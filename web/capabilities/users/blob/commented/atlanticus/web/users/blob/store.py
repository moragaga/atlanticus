# Espejo pedagógico: conserva exactamente el contrato productivo y explica su intención.
from __future__ import annotations

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
    UsersRegistryConflictError,
    UsersRegistryUnavailableError,
)
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import UsersRegistryStore

_USERS_REGISTRY_DOCUMENT_TYPE = 'atlanticus_users_registry'
_USERS_REGISTRY_SCHEMA_VERSION = 1
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
        self,
        *,
        container_name: str,
        blob_name: str,
    ) -> StorageBlobProperties: ...


# Blob conserva el registro durable compacto y usa ETag para evitar escrituras perdidas.
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
        try:
            before = self._client.get_properties(
                container_name=self._container_name,
                blob_name=self._blob_name,
            )
        except StorageBlobNotFoundError:
            return UsersRegistrySnapshot()
        except StorageError as error:
            raise UsersRegistryUnavailableError('Could not read users registry properties') from error

        before_etag = _required_etag(before)
        try:
            payload = self._client.download(
                container_name=self._container_name,
                blob_name=self._blob_name,
            )
            after = self._client.get_properties(
                container_name=self._container_name,
                blob_name=self._blob_name,
            )
        except StorageBlobNotFoundError as error:
            raise UsersRegistryConflictError('Users registry changed while it was being read') from error
        except StorageError as error:
            raise UsersRegistryUnavailableError('Could not read users registry') from error

        after_etag = _required_etag(after)
        if before_etag != after_etag:
            raise UsersRegistryConflictError('Users registry changed while it was being read')
        return UsersRegistrySnapshot(users=_decode_registry(payload), version=after_etag)

    def replace(
        self,
        users: tuple[UserRecord, ...],
        *,
        expected_version: str | None,
    ) -> UsersRegistrySnapshot:
        validated = UsersRegistrySnapshot(users=users)
        payload = _encode_registry(validated.users)
        try:
            if expected_version is None:
                self._client.upload(
                    container_name=self._container_name,
                    blob_name=self._blob_name,
                    data=payload,
                    overwrite=False,
                    content_type='application/gzip',
                )
            else:
                self._client.upload_if_match(
                    container_name=self._container_name,
                    blob_name=self._blob_name,
                    data=payload,
                    etag=expected_version,
                    content_type='application/gzip',
                )
            properties = self._client.get_properties(
                container_name=self._container_name,
                blob_name=self._blob_name,
            )
        except StorageConflictError as error:
            raise UsersRegistryConflictError('Users registry changed concurrently') from error
        except StorageError as error:
            raise UsersRegistryUnavailableError('Could not write users registry') from error
        return UsersRegistrySnapshot(users=validated.users, version=_required_etag(properties))


def _encode_registry(users: tuple[UserRecord, ...]) -> bytes:
    document = {
        'document_type': _USERS_REGISTRY_DOCUMENT_TYPE,
        'schema_version': _USERS_REGISTRY_SCHEMA_VERSION,
        'users': [user.to_document() for user in sorted(users, key=lambda item: item.user_id)],
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return gzip.compress(encoded, mtime=0)


def _decode_registry(payload: bytes) -> tuple[UserRecord, ...]:
    try:
        document = json.loads(gzip.decompress(payload).decode('utf-8'))
        if not isinstance(document, dict):
            raise TypeError
        if document.get('document_type') != _USERS_REGISTRY_DOCUMENT_TYPE:
            raise TypeError
        if document.get('schema_version') != _USERS_REGISTRY_SCHEMA_VERSION:
            raise TypeError
        raw_users = document['users']
        if not isinstance(raw_users, list) or not all(isinstance(item, dict) for item in raw_users):
            raise TypeError
        snapshot = UsersRegistrySnapshot(
            users=tuple(UserRecord.from_document(dict(item)) for item in raw_users)
        )
        return snapshot.users
    except (gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise UsersDefinitionError('Users registry document is invalid') from error


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise UsersDefinitionError(f'{field_name} has an invalid format')
    return normalized


def _required_etag(properties: StorageBlobProperties) -> str:
    etag = properties.etag
    if not isinstance(etag, str) or not etag.strip():
        raise UsersRegistryUnavailableError('Users registry blob is missing ETag')
    return etag
