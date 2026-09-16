from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosError,
    CosmosItemNotFoundError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
    CosmosQueryParameter,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.errors import UsersConfigurationProjectionError
from atlanticus.web.users.configuration.models import UserConfiguration
from atlanticus.web.users.errors import UsersDefinitionError, UsersIdentityConflictError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord, ResolvedUserRecord, RuntimeUserRecord

_PENDING_RECORD_TYPE = 'pending'
_RESOLVED_RECORD_TYPE = 'resolved'
_MANAGED_STATE_PRESENT = 'present'
_MANAGED_STATE_RETIRED = 'retired'
_RESOLVED_QUERY = 'SELECT * FROM c WHERE c.record_type = @record_type'
_HEALTH_QUERY = 'SELECT TOP 1 * FROM c'
_PROJECTION_SOURCE_KEY_FIELD = 'projection_source_key'
_PROJECTION_SOURCE_RELEASE_ID_FIELD = 'projection_source_release_id'
_PROJECTION_SOURCE_PUBLISHED_AT_FIELD = 'projection_source_published_at_utc'


class _CosmosProjectionClient(Protocol):
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, Any] | None: ...

    def create_item(
        self,
        *,
        container_name: str,
        item: Mapping[str, Any],
        include_metadata: bool = False,
    ) -> dict[str, Any]: ...

    def patch_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        operations: Sequence[CosmosPatchOperation],
        if_match_etag: str | None = None,
        include_metadata: bool = False,
    ) -> dict[str, Any]: ...

    def iter_items(
        self,
        *,
        container_name: str,
        query: str,
        parameters: Sequence[CosmosQueryParameter | Mapping[str, Any]] | None = None,
        cross_partition: bool = False,
        include_metadata: bool = False,
    ) -> Iterator[dict[str, Any]]: ...


# Materializa el ProjectionRecord CURRENT en users.runtime sin inventar revision ni reconstruir ProjectionTarget.
class CosmosUsersRuntimeProjectionMaterializer:
    def __init__(
        self,
        *,
        client: _CosmosProjectionClient,
        container_name: str,
        actor_provider: Callable[[], str],
    ) -> None:
        normalized_container_name = container_name.strip()
        if not normalized_container_name or normalized_container_name != container_name:
            raise UsersConfigurationProjectionError(
                'Users runtime projection Cosmos container name has an invalid format'
            )
        if not callable(actor_provider):
            raise TypeError('actor_provider must be callable')
        self._client = client
        self._container_name = normalized_container_name
        self._actor_provider = actor_provider

    def materialize(
        self,
        projection: ProjectionRecord[UsersProfilesConfiguration],
    ) -> None:
        if not isinstance(projection, ProjectionRecord) or not isinstance(
            projection.payload,
            UsersProfilesConfiguration,
        ):
            raise UsersConfigurationProjectionError(
                'Users runtime projection must contain UsersProfilesConfiguration'
            )
        actor = self._actor_provider()
        if not isinstance(actor, str):
            raise UsersConfigurationProjectionError('Users runtime projection actor must be text')
        normalized_actor = actor.strip()
        if not normalized_actor:
            raise UsersConfigurationProjectionError(
                'Users runtime projection actor must not be empty'
            )
        projected_at_utc = projection.projected_at_utc.isoformat()
        configured_by_id = {
            user.user_id: user for user in projection.payload.users.users
        }
        try:
            self._retire_missing_users(
                configured_ids=frozenset(configured_by_id),
                projection=projection,
                actor=normalized_actor,
                projected_at_utc=projected_at_utc,
            )
            for user in projection.payload.users.users:
                self._materialize_present_user(
                    user=user,
                    projection=projection,
                    actor=normalized_actor,
                    projected_at_utc=projected_at_utc,
                )
        except UsersConfigurationProjectionError:
            raise
        except CosmosError as error:
            raise UsersConfigurationProjectionError(
                'Could not materialize users runtime projection'
            ) from error

    def health_check(self) -> bool:
        try:
            iterator = self._client.iter_items(
                container_name=self._container_name,
                query=_HEALTH_QUERY,
                cross_partition=True,
            )
            next(iterator, None)
        except CosmosError:
            return False
        return True

    def _retire_missing_users(
        self,
        *,
        configured_ids: frozenset[str],
        projection: ProjectionRecord[UsersProfilesConfiguration],
        actor: str,
        projected_at_utc: str,
    ) -> None:
        documents = self._client.iter_items(
            container_name=self._container_name,
            query=_RESOLVED_QUERY,
            parameters=(
                CosmosQueryParameter(
                    name='@record_type',
                    value=_RESOLVED_RECORD_TYPE,
                ),
            ),
            cross_partition=True,
            include_metadata=True,
        )
        for document in documents:
            record = _record_from_document(document)
            if not isinstance(record, ResolvedUserRecord):
                raise UsersConfigurationProjectionError(
                    'Users runtime resolved query returned a non-resolved record'
                )
            managed_state = _managed_state(document)
            if record.is_local:
                if managed_state is not None:
                    raise UsersConfigurationProjectionError(
                        'Local users runtime record cannot contain managed projection state'
                    )
                continue
            if record.user_id in configured_ids:
                continue
            desired = _retired_document(
                record=record,
                projection=projection,
                actor=actor,
                projected_at_utc=projected_at_utc,
            )
            if _matches_desired_document(document=document, desired=desired):
                continue
            _require_not_newer_projection(
                document=document,
                projection=projection,
            )
            self._patch_existing(
                document=document,
                desired=desired,
                allow_concurrent_desired=True,
            )

    def _materialize_present_user(
        self,
        *,
        user: UserConfiguration,
        projection: ProjectionRecord[UsersProfilesConfiguration],
        actor: str,
        projected_at_utc: str,
    ) -> None:
        desired = _present_document(
            user=user,
            projection=projection,
            actor=actor,
            projected_at_utc=projected_at_utc,
        )
        current = self._client.find_item(
            container_name=self._container_name,
            item_id=user.user_id,
            partition_key=user.user_id,
            include_metadata=True,
        )
        if current is None:
            try:
                self._client.create_item(
                    container_name=self._container_name,
                    item=desired,
                )
                return
            except CosmosConflictError as error:
                concurrent = self._client.find_item(
                    container_name=self._container_name,
                    item_id=user.user_id,
                    partition_key=user.user_id,
                    include_metadata=True,
                )
                if concurrent is None:
                    raise UsersConfigurationProjectionError(
                        'Users runtime record disappeared after projection create conflict'
                    ) from error
                concurrent_record = _record_from_document(concurrent)
                _require_user_identity(user=user, record=concurrent_record)
                if isinstance(concurrent_record, PendingUserRecord):
                    self._patch_existing(
                        document=concurrent,
                        desired=desired,
                        allow_concurrent_desired=True,
                    )
                    return
                _require_configuration_managed_record(concurrent, concurrent_record)
                _require_not_newer_projection(
                    document=concurrent,
                    projection=projection,
                )
                if _matches_desired_document(
                    document=concurrent,
                    desired=desired,
                ):
                    return
                raise UsersConfigurationProjectionError(
                    'Users runtime record changed concurrently during projection create'
                ) from error
        record = _record_from_document(current)
        _require_user_identity(user=user, record=record)
        if isinstance(record, ResolvedUserRecord):
            _require_configuration_managed_record(current, record)
            _require_not_newer_projection(
                document=current,
                projection=projection,
            )
            if _matches_desired_document(
                document=current,
                desired=desired,
            ):
                return
        self._patch_existing(
            document=current,
            desired=desired,
            allow_concurrent_desired=True,
        )

    def _patch_existing(
        self,
        *,
        document: Mapping[str, Any],
        desired: Mapping[str, Any],
        allow_concurrent_desired: bool,
    ) -> None:
        user_id = _required_string(document, 'id')
        etag = _required_etag(document)
        operations = tuple(
            CosmosPatchOperation(operation='set', path=f'/{field}', value=value)
            for field, value in desired.items()
            if field not in {'id', '_etag'}
        )
        try:
            self._client.patch_item(
                container_name=self._container_name,
                item_id=user_id,
                partition_key=user_id,
                operations=operations,
                if_match_etag=etag,
                include_metadata=True,
            )
            return
        except CosmosPreconditionFailedError as error:
            concurrent = self._client.find_item(
                container_name=self._container_name,
                item_id=user_id,
                partition_key=user_id,
                include_metadata=True,
            )
            if concurrent is None:
                raise UsersConfigurationProjectionError(
                    'Users runtime record disappeared during projection update'
                ) from error
            _record_from_document(concurrent)
            if allow_concurrent_desired and _matches_desired_document(
                document=concurrent,
                desired=desired,
            ):
                return
            raise UsersConfigurationProjectionError(
                'Users runtime record changed concurrently during projection update'
            ) from error
        except CosmosItemNotFoundError as error:
            raise UsersConfigurationProjectionError(
                'Users runtime record disappeared during projection update'
            ) from error


# La procedencia runtime conserva SourceKey + SourceReleaseRef del ProjectionRecord.
def _projection_provenance(
    projection: ProjectionRecord[UsersProfilesConfiguration],
) -> dict[str, str]:
    return {
        _PROJECTION_SOURCE_KEY_FIELD: projection.source_key.value,
        _PROJECTION_SOURCE_RELEASE_ID_FIELD: projection.source_release_id.value,
        _PROJECTION_SOURCE_PUBLISHED_AT_FIELD: projection.source_published_at_utc.isoformat(),
    }


def _present_document(
    *,
    user: UserConfiguration,
    projection: ProjectionRecord[UsersProfilesConfiguration],
    actor: str,
    projected_at_utc: str,
) -> dict[str, Any]:
    return {
        'id': user.user_id,
        'record_type': _RESOLVED_RECORD_TYPE,
        'issuer': user.issuer,
        'subject_id': user.subject_id,
        'display_name': user.display_name,
        'email': user.email,
        'enabled': user.enabled,
        'authority_key': user.profile_key,
        'avatar_background_color': None,
        'avatar_text_color': None,
        'is_local': False,
        'managed_state': _MANAGED_STATE_PRESENT,
        **_projection_provenance(projection),
        'projected_by': actor,
        'projected_at_utc': projected_at_utc,
    }


def _retired_document(
    *,
    record: ResolvedUserRecord,
    projection: ProjectionRecord[UsersProfilesConfiguration],
    actor: str,
    projected_at_utc: str,
) -> dict[str, Any]:
    return {
        'id': record.user_id,
        'record_type': _RESOLVED_RECORD_TYPE,
        'issuer': record.issuer,
        'subject_id': record.subject_id,
        'display_name': record.display_name,
        'email': record.email,
        'enabled': False,
        'authority_key': record.authority_key,
        'avatar_background_color': record.avatar_background_color,
        'avatar_text_color': record.avatar_text_color,
        'is_local': False,
        'managed_state': _MANAGED_STATE_RETIRED,
        **_projection_provenance(projection),
        'projected_by': actor,
        'projected_at_utc': projected_at_utc,
    }


# La protección concurrente compara procedencia CURRENT y usa projected_at sólo para detectar un escritor posterior.
def _require_not_newer_projection(
    *,
    document: Mapping[str, Any],
    projection: ProjectionRecord[UsersProfilesConfiguration],
) -> None:
    provenance = (
        document.get(_PROJECTION_SOURCE_KEY_FIELD),
        document.get(_PROJECTION_SOURCE_RELEASE_ID_FIELD),
        document.get(_PROJECTION_SOURCE_PUBLISHED_AT_FIELD),
    )
    if all(value is None for value in provenance):
        return
    if not all(isinstance(value, str) and value.strip() for value in provenance):
        raise UsersConfigurationProjectionError(
            'Users runtime projection provenance is invalid'
        )
    if (
        provenance[0] == projection.source_key.value
        and provenance[1] == projection.source_release_id.value
        and provenance[2] == projection.source_published_at_utc.isoformat()
    ):
        return
    raw_projected_at = document.get('projected_at_utc')
    if raw_projected_at is None:
        return
    if not isinstance(raw_projected_at, str):
        raise UsersConfigurationProjectionError(
            'Users runtime projection timestamp must be text'
        )
    try:
        projected_at = datetime.fromisoformat(raw_projected_at)
    except ValueError as error:
        raise UsersConfigurationProjectionError(
            'Users runtime projection timestamp is invalid'
        ) from error
    if projected_at.tzinfo is None or projected_at.utcoffset() is None:
        raise UsersConfigurationProjectionError(
            'Users runtime projection timestamp must be timezone-aware'
        )
    if projected_at.astimezone(UTC) > projection.projected_at_utc:
        raise UsersConfigurationProjectionError(
            'Users runtime record belongs to a newer concurrent projection'
        )


def _record_from_document(document: Mapping[str, Any]) -> RuntimeUserRecord:
    if not isinstance(document, Mapping):
        raise UsersConfigurationProjectionError(
            'Users runtime projection document must be a mapping'
        )
    try:
        record_type = _required_string(document, 'record_type')
        user_id = _required_string(document, 'id')
        issuer = _required_string(document, 'issuer')
        subject_id = _required_string(document, 'subject_id')
        expected_user_id = build_user_key(issuer=issuer, subject_id=subject_id)
        if user_id != expected_user_id:
            raise UsersIdentityConflictError(
                'Users runtime projection document identity does not match its id'
            )
        if record_type == _PENDING_RECORD_TYPE:
            return PendingUserRecord(
                user_id=user_id,
                issuer=issuer,
                subject_id=subject_id,
                display_name=_optional_string(document, 'display_name'),
                email=_optional_string(document, 'email'),
            )
        if record_type == _RESOLVED_RECORD_TYPE:
            return ResolvedUserRecord(
                user_id=user_id,
                issuer=issuer,
                subject_id=subject_id,
                display_name=_required_string(document, 'display_name'),
                email=_optional_string(document, 'email'),
                enabled=_required_bool(document, 'enabled'),
                authority_key=_required_string(document, 'authority_key'),
                avatar_background_color=_optional_string(
                    document,
                    'avatar_background_color',
                ),
                avatar_text_color=_optional_string(
                    document,
                    'avatar_text_color',
                ),
                is_local=_optional_bool(document, 'is_local', default=False),
            )
        raise UsersDefinitionError(
            f'Unsupported users runtime record type: {record_type!r}'
        )
    except (UsersDefinitionError, UsersIdentityConflictError) as error:
        raise UsersConfigurationProjectionError(
            'Users runtime projection document is invalid'
        ) from error


def _require_user_identity(
    *,
    user: UserConfiguration,
    record: RuntimeUserRecord,
) -> None:
    if (
        record.user_id != user.user_id
        or record.issuer != user.issuer
        or record.subject_id != user.subject_id
    ):
        raise UsersConfigurationProjectionError(
            'Users runtime record identity conflicts with configuration source'
        )


def _require_configuration_managed_record(
    document: Mapping[str, Any],
    record: ResolvedUserRecord,
) -> None:
    managed_state = _managed_state(document)
    if record.is_local:
        raise UsersConfigurationProjectionError(
            'Managed users configuration collides with a local users runtime record'
        )
    if managed_state not in {
        None,
        _MANAGED_STATE_PRESENT,
        _MANAGED_STATE_RETIRED,
    }:
        raise UsersConfigurationProjectionError(
            'Users runtime managed state is invalid'
        )


def _managed_state(document: Mapping[str, Any]) -> str | None:
    value = document.get('managed_state')
    if value is None:
        return None
    if not isinstance(value, str) or value not in {
        _MANAGED_STATE_PRESENT,
        _MANAGED_STATE_RETIRED,
    }:
        raise UsersConfigurationProjectionError(
            'Users runtime managed state is invalid'
        )
    return value


def _matches_desired_document(
    *,
    document: Mapping[str, Any],
    desired: Mapping[str, Any],
) -> bool:
    ignored = {'projected_by', 'projected_at_utc'}
    return all(
        document.get(key) == value
        for key, value in desired.items()
        if key not in ignored
    )


def _required_etag(document: Mapping[str, Any]) -> str:
    value = document.get('_etag')
    if not isinstance(value, str) or not value.strip():
        raise UsersConfigurationProjectionError(
            'Users runtime projection document is missing ETag'
        )
    return value


def _required_string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UsersDefinitionError(
            f'Users runtime field {key!r} must be non-empty text'
        )
    return value


def _optional_string(
    document: Mapping[str, Any],
    key: str,
) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise UsersDefinitionError(
            f'Users runtime field {key!r} must be text or null'
        )
    return value


def _required_bool(document: Mapping[str, Any], key: str) -> bool:
    value = document.get(key)
    if not isinstance(value, bool):
        raise UsersDefinitionError(
            f'Users runtime field {key!r} must be boolean'
        )
    return value


def _optional_bool(
    document: Mapping[str, Any],
    key: str,
    *,
    default: bool,
) -> bool:
    value = document.get(key, default)
    if not isinstance(value, bool):
        raise UsersDefinitionError(
            f'Users runtime field {key!r} must be boolean'
        )
    return value
