from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosError,
    CosmosItemNotFoundError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
    CosmosQueryParameter,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import (
    UserAlreadyPromotedError,
    UsersDefinitionError,
    UsersIdentityConflictError,
    UsersStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord
from atlanticus.web.users.store import UsersAdministrationStore, UsersRuntimeStore

_USER_DOCUMENT_TYPE = 'atlanticus_user'
_USER_SCHEMA_VERSION = 2
_USERS_QUERY = 'SELECT * FROM c WHERE c.document_type = @document_type'


class _CosmosClient(Protocol):
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

    def query_items(
        self,
        *,
        container_name: str,
        query: str,
        parameters: Sequence[CosmosQueryParameter | Mapping[str, Any]] | None = None,
        cross_partition: bool = False,
    ) -> tuple[dict[str, Any], ...]: ...


class CosmosUsersStore(UsersRuntimeStore, UsersAdministrationStore):
    def __init__(self, *, client: _CosmosClient, container_name: str) -> None:
        normalized_container_name = container_name.strip()
        if not normalized_container_name or normalized_container_name != container_name:
            raise UsersDefinitionError('Users Cosmos container name has an invalid format')
        self._client = client
        self._container_name = normalized_container_name

    def resolve(self, identity: AuthenticatedIdentity) -> UserRecord | None:
        user_id = _user_id(identity)
        user = self.get(user_id)
        if user is None:
            return None
        _require_identity_match(identity=identity, user=user)
        return user

    def get(self, user_id: str) -> UserRecord | None:
        normalized_user_id = _required_user_id(user_id)
        try:
            document = self._client.find_item(
                container_name=self._container_name,
                item_id=normalized_user_id,
                partition_key=normalized_user_id,
            )
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not read users store') from error
        if document is None:
            return None
        return _user_from_document(document)

    def list_users(self) -> tuple[UserRecord, ...]:
        try:
            documents = self._client.query_items(
                container_name=self._container_name,
                query=_USERS_QUERY,
                parameters=(
                    CosmosQueryParameter(name='@document_type', value=_USER_DOCUMENT_TYPE),
                ),
                cross_partition=True,
            )
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not list promoted users') from error
        users = tuple(_user_from_document(document) for document in documents)
        return tuple(sorted(users, key=lambda user: user.user_id))

    def create(self, user: UserRecord) -> UserRecord:
        if not isinstance(user, UserRecord):
            raise TypeError('user must be UserRecord')
        try:
            saved = self._client.create_item(
                container_name=self._container_name,
                item=_user_to_document(user),
            )
        except CosmosConflictError as error:
            raise UserAlreadyPromotedError('User is already promoted') from error
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not create promoted user') from error
        persisted = _user_from_document(saved)
        if persisted != user:
            raise UsersStoreUnavailableError('Cosmos persisted a different user')
        return persisted

    def replace(self, user: UserRecord) -> UserRecord:
        if not isinstance(user, UserRecord):
            raise TypeError('user must be UserRecord')
        try:
            current = self._client.find_item(
                container_name=self._container_name,
                item_id=user.user_id,
                partition_key=user.user_id,
                include_metadata=True,
            )
            if current is None:
                raise UsersStoreUnavailableError('Promoted user does not exist')
            current_user = _user_from_document(current)
            if (current_user.issuer, current_user.subject_id) != (
                user.issuer,
                user.subject_id,
            ):
                raise UsersIdentityConflictError('Promoted user identity cannot be changed')
            etag = _required_etag(current)
            desired = _user_to_document(user)
            operations = tuple(
                CosmosPatchOperation(operation='set', path=f'/{field}', value=value)
                for field, value in desired.items()
                if field != 'id'
            )
            saved = self._client.patch_item(
                container_name=self._container_name,
                item_id=user.user_id,
                partition_key=user.user_id,
                operations=operations,
                if_match_etag=etag,
            )
        except (UsersIdentityConflictError, UsersStoreUnavailableError):
            raise
        except CosmosItemNotFoundError as error:
            raise UsersStoreUnavailableError('Promoted user disappeared during update') from error
        except CosmosPreconditionFailedError as error:
            raise UsersStoreUnavailableError('Promoted user changed concurrently') from error
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not update promoted user') from error
        persisted = _user_from_document(saved)
        if persisted != user:
            raise UsersStoreUnavailableError('Cosmos persisted a different user')
        return persisted


def _user_id(identity: AuthenticatedIdentity) -> str:
    if not isinstance(identity, AuthenticatedIdentity):
        raise UsersDefinitionError('identity must be AuthenticatedIdentity')
    return build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)


def _required_user_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError('user_id must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise UsersDefinitionError('User id has an invalid format')
    return normalized


def _user_to_document(user: UserRecord) -> dict[str, object]:
    return {
        'id': user.user_id,
        'document_type': _USER_DOCUMENT_TYPE,
        'schema_version': _USER_SCHEMA_VERSION,
        'issuer': user.issuer,
        'subject_id': user.subject_id,
        'display_name': user.display_name,
        'email': user.email,
        'enabled': user.enabled,
        'profile_key': user.profile_key,
        'avatar_background_color': user.avatar_background_color,
        'avatar_text_color': user.avatar_text_color,
    }


def _user_from_document(document: Mapping[str, Any]) -> UserRecord:
    if not isinstance(document, Mapping):
        raise UsersDefinitionError('Users Cosmos document must be a mapping')
    if document.get('document_type') != _USER_DOCUMENT_TYPE:
        raise UsersDefinitionError('Users Cosmos document type is invalid')
    if document.get('schema_version') != _USER_SCHEMA_VERSION:
        raise UsersDefinitionError('Users Cosmos schema version is invalid')
    try:
        user = UserRecord(
            user_id=_required_string(document, 'id'),
            issuer=_required_string(document, 'issuer'),
            subject_id=_required_string(document, 'subject_id'),
            display_name=_required_string(document, 'display_name'),
            email=_optional_string(document, 'email'),
            enabled=_required_bool(document, 'enabled'),
            profile_key=_required_string(document, 'profile_key'),
            avatar_background_color=_optional_string(document, 'avatar_background_color'),
            avatar_text_color=_optional_string(document, 'avatar_text_color'),
        )
    except UsersDefinitionError:
        raise
    if user.user_id != _required_string(document, 'id'):
        raise UsersIdentityConflictError('Users Cosmos document identity does not match its id')
    return user


def _require_identity_match(*, identity: AuthenticatedIdentity, user: UserRecord) -> None:
    expected_user_id = build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)
    if (
        user.user_id != expected_user_id
        or user.issuer != identity.issuer
        or user.subject_id != identity.subject_id
    ):
        raise UsersIdentityConflictError('Users Cosmos user does not match authenticated identity')


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


def _required_etag(document: Mapping[str, Any]) -> str:
    value = document.get('_etag')
    if not isinstance(value, str) or not value.strip():
        raise UsersStoreUnavailableError('Users Cosmos document is missing ETag')
    return value
