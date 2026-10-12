from __future__ import annotations

# El Cosmos pertenece a una Tool; users-runtime no repite application/tool en ids, consultas ni documentos.

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
    UsersDefinitionError,
    UsersIdentityConflictError,
    UsersStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore

_USER_DOCUMENT_TYPE = 'atlanticus_tool_runtime_user'
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
        include_metadata: bool = False,
    ) -> tuple[dict[str, Any], ...]: ...

    def delete_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        if_match_etag: str | None = None,
    ) -> None: ...


class CosmosUsersRuntimeStore(UsersRuntimeStore):
    def __init__(self, *, client: _CosmosClient, container_name: str) -> None:
        normalized_container_name = container_name.strip()
        if not normalized_container_name or normalized_container_name != container_name:
            raise UsersDefinitionError('Users Cosmos container name has an invalid format')
        self._client = client
        self._container_name = normalized_container_name

    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUser | None:
        if not isinstance(identity, AuthenticatedIdentity):
            raise UsersDefinitionError('identity must be AuthenticatedIdentity')
        user_id = build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)
        try:
            document = self._client.find_item(
                container_name=self._container_name,
                item_id=user_id,
                partition_key=user_id,
            )
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not read users runtime') from error
        if document is None:
            return None
        user = _user_from_document(document)
        if user.user_id != user_id or user.issuer != identity.issuer or user.subject_id != identity.subject_id:
            raise UsersIdentityConflictError('Users runtime user does not match authenticated identity')
        return user

    def list_users(self) -> tuple[RuntimeUser, ...]:
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
            raise UsersStoreUnavailableError('Could not list users runtime') from error
        users = tuple(_user_from_document(document) for document in documents)
        return tuple(sorted(users, key=lambda user: user.user_id))

    # Publicación de campos base con ETag; preserva los campos de ADA.
    def upsert_base_user(self, user: RuntimeUser) -> RuntimeUser:
        if not isinstance(user, RuntimeUser):
            raise TypeError('Users base publication requires RuntimeUser')
        for _attempt in range(4):
            try:
                existing = self._client.find_item(
                    container_name=self._container_name,
                    item_id=user.user_id,
                    partition_key=user.user_id,
                    include_metadata=True,
                )
                if existing is None:
                    try:
                        self._client.create_item(
                            container_name=self._container_name,
                            item=_user_to_document(user),
                        )
                    except CosmosConflictError:
                        continue
                else:
                    previous = _user_from_document(existing)
                    if previous.issuer != user.issuer or previous.subject_id != user.subject_id:
                        raise UsersIdentityConflictError('Runtime user identity cannot be changed')
                    if (
                        previous.identity == user.identity
                        and previous.enabled == user.enabled
                        and previous.profile == user.profile
                    ):
                        return previous
                    try:
                        self._client.patch_item(
                            container_name=self._container_name,
                            item_id=user.user_id,
                            partition_key=user.user_id,
                            operations=(
                                CosmosPatchOperation('set', '/user/identity', user.identity.to_document()),
                                CosmosPatchOperation('set', '/user/enabled', user.enabled),
                                CosmosPatchOperation('set', '/user/profile', user.profile.to_document()),
                            ),
                            if_match_etag=_etag(existing),
                        )
                    except (CosmosConflictError, CosmosItemNotFoundError):
                        continue
                persisted = self._client.find_item(
                    container_name=self._container_name,
                    item_id=user.user_id,
                    partition_key=user.user_id,
                )
                if persisted is not None:
                    result = _user_from_document(persisted)
                    if (
                        result.identity == user.identity
                        and result.enabled == user.enabled
                        and result.profile == user.profile
                    ):
                        return result
            except (UsersIdentityConflictError, UsersDefinitionError):
                raise
            except CosmosError as error:
                raise UsersStoreUnavailableError('Could not publish users base') from error
        raise UsersStoreUnavailableError('Users base publication changed concurrently')

    # Actualiza una sola partición. Nunca utiliza replace_all para cambios individuales.
    def upsert_user_if_current(
        self, user: RuntimeUser, *, expected: RuntimeUser | None
    ) -> RuntimeUser:
        if not isinstance(user, RuntimeUser):
            raise TypeError('Conditional runtime publication requires RuntimeUser')
        if expected is not None and not isinstance(expected, RuntimeUser):
            raise TypeError('Expected runtime user must be RuntimeUser or None')
        if expected is not None and expected.user_id != user.user_id:
            raise UsersIdentityConflictError('Conditional publication identity mismatch')
        try:
            document = self._client.find_item(
                container_name=self._container_name,
                item_id=user.user_id,
                partition_key=user.user_id,
                include_metadata=True,
            )
            current = None if document is None else _user_from_document(document)
            if current != expected:
                raise UsersIdentityConflictError('Runtime user changed during conditional publication')
            if current is None:
                self._client.create_item(
                    container_name=self._container_name, item=_user_to_document(user),
                )
            elif current != user:
                self._client.patch_item(
                    container_name=self._container_name,
                    item_id=user.user_id,
                    partition_key=user.user_id,
                    operations=(CosmosPatchOperation('set', '/user', user.to_document()),),
                    if_match_etag=_etag(document),
                )
            persisted = self._client.find_item(
                container_name=self._container_name,
                item_id=user.user_id,
                partition_key=user.user_id,
            )
        except (CosmosConflictError, CosmosItemNotFoundError, CosmosPreconditionFailedError) as error:
            raise UsersIdentityConflictError('Runtime user changed during conditional publication') from error
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not conditionally publish runtime user') from error
        if persisted is None:
            raise UsersStoreUnavailableError('Published runtime user could not be read')
        result = _user_from_document(persisted)
        if result != user:
            raise UsersStoreUnavailableError('Conditional runtime publication differs from request')
        return result

    def upsert_user(self, user: RuntimeUser) -> RuntimeUser:
        if not isinstance(user, RuntimeUser):
            raise TypeError('Users runtime upsert requires RuntimeUser')
        payload = _user_to_document(user)
        try:
            existing = self._client.find_item(
                container_name=self._container_name,
                item_id=user.user_id,
                partition_key=user.user_id,
                include_metadata=True,
            )
            if existing is None:
                self._client.create_item(container_name=self._container_name, item=payload)
            else:
                previous = _user_from_document(existing)
                if previous.issuer != user.issuer or previous.subject_id != user.subject_id:
                    raise UsersIdentityConflictError('Runtime user identity cannot be changed')
                if previous != user:
                    self._client.patch_item(
                        container_name=self._container_name,
                        item_id=user.user_id,
                        partition_key=user.user_id,
                        operations=(
                            CosmosPatchOperation(
                                operation='set', path='/user', value=user.to_document()
                            ),
                        ),
                        if_match_etag=_etag(existing),
                    )
            persisted = self._client.find_item(
                container_name=self._container_name,
                item_id=user.user_id,
                partition_key=user.user_id,
            )
        except CosmosConflictError as error:
            raise UsersStoreUnavailableError('Users runtime changed concurrently') from error
        except CosmosItemNotFoundError as error:
            raise UsersStoreUnavailableError('Users runtime changed during publication') from error
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not publish runtime user') from error
        # Releer Cosmos evita confirmar como exitosa una escritura que no persistió igual.
        if persisted is None:
            raise UsersStoreUnavailableError('Published runtime user could not be read')
        result = _user_from_document(persisted)
        if result != user:
            raise UsersStoreUnavailableError('Published runtime user differs from request')
        return result

    def replace_all(self, users: tuple[RuntimeUser, ...]) -> tuple[RuntimeUser, ...]:
        desired = tuple(sorted(users, key=lambda user: user.user_id))
        if any(not isinstance(user, RuntimeUser) for user in desired):
            raise TypeError('users must contain RuntimeUser entries')
        if len({user.user_id for user in desired}) != len(desired):
            raise UsersDefinitionError('Users runtime replacement contains duplicate ids')
        try:
            current_documents = self._client.query_items(
                container_name=self._container_name,
                query=_USERS_QUERY,
                parameters=(
                    CosmosQueryParameter(name='@document_type', value=_USER_DOCUMENT_TYPE),
                ),
                cross_partition=True,
                include_metadata=True,
            )
            current = {
                _user_from_document(document).user_id: document
                for document in current_documents
            }
            desired_by_id = {user.user_id: user for user in desired}

            for user_id, user in desired_by_id.items():
                payload = _user_to_document(user)
                existing = current.get(user_id)
                if existing is None:
                    self._client.create_item(
                        container_name=self._container_name,
                        item=payload,
                    )
                    continue
                existing_user = _user_from_document(existing)
                if (
                    existing_user.issuer != user.issuer
                    or existing_user.subject_id != user.subject_id
                ):
                    raise UsersIdentityConflictError('Runtime user identity cannot be changed')
                if existing_user == user:
                    continue
                operations = tuple(
                    CosmosPatchOperation(operation='set', path=f'/{key}', value=value)
                    for key, value in payload.items()
                    if key != 'id'
                )
                self._client.patch_item(
                    container_name=self._container_name,
                    item_id=user_id,
                    partition_key=user_id,
                    operations=operations,
                    if_match_etag=_etag(existing),
                )

            for user_id, existing in current.items():
                if user_id in desired_by_id:
                    continue
                self._client.delete_item(
                    container_name=self._container_name,
                    item_id=user_id,
                    partition_key=user_id,
                    if_match_etag=_etag(existing),
                )
        except (UsersIdentityConflictError, UsersStoreUnavailableError):
            raise
        except CosmosConflictError as error:
            raise UsersStoreUnavailableError('Users runtime changed concurrently') from error
        except CosmosItemNotFoundError as error:
            raise UsersStoreUnavailableError('Users runtime changed during replacement') from error
        except CosmosError as error:
            raise UsersStoreUnavailableError('Could not replace users runtime') from error

        persisted = self.list_users()
        if persisted != desired:
            raise UsersStoreUnavailableError('Users runtime replacement could not be verified')
        return persisted


def _user_to_document(user: RuntimeUser) -> dict[str, object]:
    return {
        'id': user.user_id,
        'document_type': _USER_DOCUMENT_TYPE,
        'schema_version': _USER_SCHEMA_VERSION,
        'user': user.to_document(),
    }


def _user_from_document(document: Mapping[str, Any]) -> RuntimeUser:
    if not isinstance(document, Mapping):
        raise UsersDefinitionError('Users Cosmos document must be a mapping')
    if document.get('document_type') != _USER_DOCUMENT_TYPE:
        raise UsersDefinitionError('Users Cosmos document type is invalid')
    if document.get('schema_version') != _USER_SCHEMA_VERSION:
        raise UsersDefinitionError('Users Cosmos schema version is invalid')
    raw = document.get('user')
    if not isinstance(raw, dict):
        raise UsersDefinitionError('Users Cosmos runtime payload is invalid')
    user = RuntimeUser.from_document(raw)
    if document.get('id') != user.user_id:
        raise UsersIdentityConflictError('Users Cosmos document id does not match runtime user')
    return user


def _etag(document: Mapping[str, Any]) -> str:
    value = document.get('_etag')
    if not isinstance(value, str) or not value.strip():
        raise UsersStoreUnavailableError('Users Cosmos document is missing ETag')
    return value
