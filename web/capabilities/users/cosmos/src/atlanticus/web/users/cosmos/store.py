from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosError,
    CosmosQueryParameter,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import (
    UsersDefinitionError,
    UsersIdentityConflictError,
    UsersRuntimeStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord, ResolvedUserRecord, RuntimeUserRecord
from atlanticus.web.users.store import PendingUsersReader, UsersRuntimeStore

_PENDING_RECORD_TYPE = 'pending'
_RESOLVED_RECORD_TYPE = 'resolved'
_PENDING_QUERY = 'SELECT * FROM c WHERE c.record_type = @record_type'


class _CosmosClient(Protocol):
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
    ) -> dict[str, Any] | None: ...

    def create_item(
        self,
        *,
        container_name: str,
        item: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def query_items(
        self,
        *,
        container_name: str,
        query: str,
        parameters: Sequence[CosmosQueryParameter | Mapping[str, Any]] | None = None,
        cross_partition: bool = False,
    ) -> tuple[dict[str, Any], ...]: ...


class CosmosUsersRuntimeStore(UsersRuntimeStore, PendingUsersReader):
    def __init__(self, *, client: _CosmosClient, container_name: str) -> None:
        normalized_container_name = container_name.strip()
        if not normalized_container_name or normalized_container_name != container_name:
            raise UsersDefinitionError('Users Cosmos container name has an invalid format')
        self._client = client
        self._container_name = normalized_container_name

    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord | None:
        user_id = _user_id(identity)
        try:
            document = self._client.find_item(
                container_name=self._container_name,
                item_id=user_id,
                partition_key=user_id,
            )
        except CosmosError as error:
            raise UsersRuntimeStoreUnavailableError('Could not read users runtime store') from error
        if document is None:
            return None
        record = _record_from_document(document)
        _require_identity_match(identity=identity, record=record)
        return record

    def observe(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord:
        user_id = _user_id(identity)
        document = {
            'id': user_id,
            'record_type': _PENDING_RECORD_TYPE,
            'issuer': identity.issuer,
            'subject_id': identity.subject_id,
            'display_name': identity.display_name,
            'email': identity.email,
        }
        try:
            created = self._client.create_item(
                container_name=self._container_name,
                item=document,
            )
        except CosmosConflictError as error:
            current = self.resolve(identity)
            if current is None:
                raise UsersRuntimeStoreUnavailableError(
                    'Users runtime record disappeared after observation conflict'
                ) from error
            return current
        except CosmosError as error:
            raise UsersRuntimeStoreUnavailableError(
                'Could not observe users runtime identity'
            ) from error
        record = _record_from_document(created)
        _require_identity_match(identity=identity, record=record)
        return record

    def list_pending(self) -> tuple[PendingUserRecord, ...]:
        try:
            documents = self._client.query_items(
                container_name=self._container_name,
                query=_PENDING_QUERY,
                parameters=(CosmosQueryParameter(name='@record_type', value=_PENDING_RECORD_TYPE),),
                cross_partition=True,
            )
        except CosmosError as error:
            raise UsersRuntimeStoreUnavailableError('Could not list pending users') from error
        records: list[PendingUserRecord] = []
        for document in documents:
            record = _record_from_document(document)
            if not isinstance(record, PendingUserRecord):
                raise UsersDefinitionError('Pending users query returned a non-pending record')
            records.append(record)
        return tuple(sorted(records, key=lambda record: record.user_id))


def _user_id(identity: AuthenticatedIdentity) -> str:
    if not isinstance(identity, AuthenticatedIdentity):
        raise UsersDefinitionError('identity must be AuthenticatedIdentity')
    return build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)


def _record_from_document(document: Mapping[str, Any]) -> RuntimeUserRecord:
    if not isinstance(document, Mapping):
        raise UsersDefinitionError('Users Cosmos document must be a mapping')
    record_type = _required_string(document, 'record_type')
    user_id = _required_string(document, 'id')
    issuer = _required_string(document, 'issuer')
    subject_id = _required_string(document, 'subject_id')
    expected_user_id = build_user_key(issuer=issuer, subject_id=subject_id)
    if user_id != expected_user_id:
        raise UsersIdentityConflictError('Users Cosmos document identity does not match its id')
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
            avatar_background_color=_optional_string(document, 'avatar_background_color'),
            avatar_text_color=_optional_string(document, 'avatar_text_color'),
            is_local=_optional_bool(document, 'is_local', default=False),
        )
    raise UsersDefinitionError(f'Unsupported users Cosmos record type: {record_type!r}')


def _require_identity_match(
    *,
    identity: AuthenticatedIdentity,
    record: RuntimeUserRecord,
) -> None:
    expected_user_id = build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)
    if (
        record.user_id != expected_user_id
        or record.issuer != identity.issuer
        or record.subject_id != identity.subject_id
    ):
        raise UsersIdentityConflictError(
            'Users Cosmos record does not match authenticated identity'
        )


def _required_string(document: Mapping[str, Any], field_name: str) -> str:
    value = document.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise UsersDefinitionError(f'Users Cosmos field {field_name!r} must be non-empty text')
    return value


def _optional_string(document: Mapping[str, Any], field_name: str) -> str | None:
    value = document.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise UsersDefinitionError(f'Users Cosmos field {field_name!r} must be text or null')
    return value


def _required_bool(document: Mapping[str, Any], field_name: str) -> bool:
    value = document.get(field_name)
    if not isinstance(value, bool):
        raise UsersDefinitionError(f'Users Cosmos field {field_name!r} must be boolean')
    return value


def _optional_bool(
    document: Mapping[str, Any],
    field_name: str,
    *,
    default: bool,
) -> bool:
    if field_name not in document:
        return default
    return _required_bool(document, field_name)
