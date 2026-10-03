from __future__ import annotations

# Registry global y Membership Tool usan documentos Blob independientes con ETag.

import gzip
import json
from collections.abc import Mapping
from typing import Protocol

from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageConflictError,
    StorageError,
)
from atlanticus.connectivity.storage.models import StorageBlobProperties
from atlanticus.web.users.errors import (
    UsersDefinitionError,
    UsersMembershipConflictError,
    UsersMembershipUnavailableError,
    UsersRegistryConflictError,
    UsersRegistryUnavailableError,
)
from atlanticus.web.users.models import (
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.store import ToolMembershipStore, UsersRegistryStore

_USERS_REGISTRY_DOCUMENT_TYPE = 'atlanticus_users_registry'
_USERS_REGISTRY_SCHEMA_VERSION = 3
_MEMBERSHIP_DOCUMENT_TYPE = 'atlanticus_tool_user_memberships'
_MEMBERSHIP_SCHEMA_VERSION = 1
_DEFAULT_BLOB_NAME = 'users/users.json.gz'


class _StorageClient(Protocol):
    def download(self, *, container_name: str, blob_name: str) -> bytes: ...
    def upload(
        self,
        *,
        container_name: str,
        blob_name: str,
        data: bytes,
        overwrite: bool = True,
        metadata: Mapping[str, str] | None = None,
        content_type: str | None = None,
    ) -> None: ...
    def upload_if_match(
        self,
        *,
        container_name: str,
        blob_name: str,
        data: bytes,
        etag: str,
        metadata: Mapping[str, str] | None = None,
        content_type: str | None = None,
    ) -> None: ...
    def get_properties(
        self, *, container_name: str, blob_name: str
    ) -> StorageBlobProperties: ...


class BlobUsersRegistryStore(UsersRegistryStore):
    def __init__(
        self,
        *,
        client: _StorageClient,
        container_name: str,
        blob_name: str = _DEFAULT_BLOB_NAME,
    ) -> None:
        self._client = client
        self._container_name = _required_text(container_name, 'container_name')
        self._blob_name = _required_text(blob_name, 'blob_name')

    def load(self) -> UsersRegistrySnapshot:
        return _read_snapshot(
            client=self._client,
            container_name=self._container_name,
            blob_name=self._blob_name,
            empty=UsersRegistrySnapshot(),
            decode=_decode_registry,
            unavailable=UsersRegistryUnavailableError,
            conflict=UsersRegistryConflictError,
            description='users registry',
        )

    def replace(
        self,
        users: tuple[UserIdentity, ...],
        *,
        expected_version: str | None,
    ) -> UsersRegistrySnapshot:
        validated = UsersRegistrySnapshot(users=users)
        version = _write_snapshot(
            client=self._client,
            container_name=self._container_name,
            blob_name=self._blob_name,
            payload=_encode_registry(validated.users),
            expected_version=expected_version,
            unavailable=UsersRegistryUnavailableError,
            conflict=UsersRegistryConflictError,
            description='users registry',
        )
        return UsersRegistrySnapshot(users=validated.users, version=version)


class BlobToolMembershipStore(ToolMembershipStore):
    def __init__(
        self,
        *,
        client: _StorageClient,
        container_name: str,
        blob_name: str,
    ) -> None:
        self._client = client
        self._container_name = _required_text(container_name, 'container_name')
        self._blob_name = _required_text(blob_name, 'blob_name')

    def load(self) -> ToolMembershipSnapshot:
        return _read_snapshot(
            client=self._client,
            container_name=self._container_name,
            blob_name=self._blob_name,
            empty=ToolMembershipSnapshot(),
            decode=_decode_memberships,
            unavailable=UsersMembershipUnavailableError,
            conflict=UsersMembershipConflictError,
            description='Tool membership registry',
        )

    def replace(
        self,
        memberships: tuple[ToolUserMembership, ...],
        *,
        expected_version: str | None,
    ) -> ToolMembershipSnapshot:
        validated = ToolMembershipSnapshot(memberships=memberships)
        version = _write_snapshot(
            client=self._client,
            container_name=self._container_name,
            blob_name=self._blob_name,
            payload=_encode_memberships(validated.memberships),
            expected_version=expected_version,
            unavailable=UsersMembershipUnavailableError,
            conflict=UsersMembershipConflictError,
            description='Tool membership registry',
        )
        return ToolMembershipSnapshot(memberships=validated.memberships, version=version)


def _read_snapshot(
    *,
    client: _StorageClient,
    container_name: str,
    blob_name: str,
    empty,
    decode,
    unavailable,
    conflict,
    description: str,
):
    try:
        before = client.get_properties(container_name=container_name, blob_name=blob_name)
    except StorageBlobNotFoundError:
        return empty
    except StorageError as error:
        raise unavailable(f'Could not read {description} properties') from error
    before_etag = _required_etag(before, unavailable, description)
    try:
        payload = client.download(container_name=container_name, blob_name=blob_name)
        after = client.get_properties(container_name=container_name, blob_name=blob_name)
    except StorageBlobNotFoundError as error:
        raise conflict(f'{description} changed while it was being read') from error
    except StorageError as error:
        raise unavailable(f'Could not read {description}') from error
    after_etag = _required_etag(after, unavailable, description)
    if before_etag != after_etag:
        raise conflict(f'{description} changed while it was being read')
    value = decode(payload)
    return type(empty)(**{
        ('users' if isinstance(empty, UsersRegistrySnapshot) else 'memberships'): value,
        'version': after_etag,
    })


def _write_snapshot(
    *,
    client: _StorageClient,
    container_name: str,
    blob_name: str,
    payload: bytes,
    expected_version: str | None,
    unavailable,
    conflict,
    description: str,
) -> str:
    try:
        if expected_version is None:
            client.upload(
                container_name=container_name,
                blob_name=blob_name,
                data=payload,
                overwrite=False,
                content_type='application/gzip',
            )
        else:
            client.upload_if_match(
                container_name=container_name,
                blob_name=blob_name,
                data=payload,
                etag=expected_version,
                content_type='application/gzip',
            )
        properties = client.get_properties(container_name=container_name, blob_name=blob_name)
    except StorageConflictError as error:
        raise conflict(f'{description} changed concurrently') from error
    except StorageError as error:
        raise unavailable(f'Could not write {description}') from error
    return _required_etag(properties, unavailable, description)


def _encode_registry(users: tuple[UserIdentity, ...]) -> bytes:
    return _gzip_document({
        'document_type': _USERS_REGISTRY_DOCUMENT_TYPE,
        'schema_version': _USERS_REGISTRY_SCHEMA_VERSION,
        'users': [user.to_document() for user in sorted(users, key=lambda item: item.user_id)],
    })


def _decode_registry(payload: bytes) -> tuple[UserIdentity, ...]:
    document = _ungzip_document(payload)
    try:
        if (
            document.get('document_type') != _USERS_REGISTRY_DOCUMENT_TYPE
            or document.get('schema_version') != _USERS_REGISTRY_SCHEMA_VERSION
        ):
            raise TypeError
        raw = document['users']
        if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
            raise TypeError
        return UsersRegistrySnapshot(
            users=tuple(UserIdentity.from_document(dict(item)) for item in raw)
        ).users
    except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
        raise UsersDefinitionError('Users registry document is invalid') from error


def _encode_memberships(memberships: tuple[ToolUserMembership, ...]) -> bytes:
    return _gzip_document({
        'document_type': _MEMBERSHIP_DOCUMENT_TYPE,
        'schema_version': _MEMBERSHIP_SCHEMA_VERSION,
        'memberships': [
            item.to_document() for item in sorted(memberships, key=lambda value: value.user_id)
        ],
    })


def _decode_memberships(payload: bytes) -> tuple[ToolUserMembership, ...]:
    document = _ungzip_document(payload)
    try:
        if (
            document.get('document_type') != _MEMBERSHIP_DOCUMENT_TYPE
            or document.get('schema_version') != _MEMBERSHIP_SCHEMA_VERSION
        ):
            raise TypeError
        raw = document['memberships']
        if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
            raise TypeError
        return ToolMembershipSnapshot(
            memberships=tuple(ToolUserMembership.from_document(dict(item)) for item in raw)
        ).memberships
    except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
        raise UsersDefinitionError('Tool membership document is invalid') from error


def _gzip_document(document: dict[str, object]) -> bytes:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')
    return gzip.compress(encoded, mtime=0)


def _ungzip_document(payload: bytes) -> dict[str, object]:
    try:
        document = json.loads(gzip.decompress(payload).decode('utf-8'))
        if not isinstance(document, dict):
            raise TypeError
        return document
    except (gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise UsersDefinitionError('Users Blob document is invalid') from error


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise UsersDefinitionError(f'{field_name} has an invalid format')
    return normalized


def _required_etag(properties: StorageBlobProperties, unavailable, description: str) -> str:
    etag = properties.etag
    if not isinstance(etag, str) or not etag.strip():
        raise unavailable(f'{description} blob is missing ETag')
    return etag
