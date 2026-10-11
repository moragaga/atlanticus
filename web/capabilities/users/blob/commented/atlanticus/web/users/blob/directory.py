from __future__ import annotations

# El directorio contiene únicamente candidatos: no crea Registry, Membership ni RuntimeUser.
# El archivo se identifica por el user_id canónico, impidiendo colisiones por nombre o correo.

import json
from typing import Protocol

from atlanticus.connectivity.storage import StorageError
from atlanticus.connectivity.storage.models import StorageBlobProperties
from atlanticus.web.users.errors import UsersDefinitionError, UsersStoreUnavailableError
from atlanticus.web.users.models import DiscoveredUser
from atlanticus.web.users.store import UsersDirectoryReader

_DOCUMENT_TYPE = 'atlanticus_discovered_user'
_SCHEMA_VERSION = 1
_MAX_DOCUMENT_BYTES = 16_384


class _StorageClient(Protocol):
    # Esta interfaz reducida desacopla la lectura del SDK de Azure Storage.
    def list_blobs(
        self, *, container_name: str, prefix: str | None = None, max_items: int | None = None
    ) -> tuple[StorageBlobProperties, ...]: ...

    def download(self, *, container_name: str, blob_name: str) -> bytes: ...


class BlobUsersDirectoryReader(UsersDirectoryReader):
    def __init__(
        self, *, client: _StorageClient, container_name: str, prefix: str, max_items: int = 200
    ) -> None:
        if not container_name or container_name != container_name.strip():
            raise UsersDefinitionError('Users directory container name is invalid')
        if not prefix or prefix != prefix.strip().strip('/'):
            raise UsersDefinitionError('Users directory prefix is invalid')
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
            raise UsersDefinitionError('Users directory max_items must be positive')
        self._client = client
        self._container_name = container_name
        self._prefix = prefix
        self._max_items = max_items

    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        base = f'{self._prefix}/'
        try:
            # Enumeración acotada: un directorio demasiado grande falla sin truncar usuarios.
            blobs = self._client.list_blobs(
                container_name=self._container_name, prefix=base, max_items=self._max_items
            )
        except StorageError as error:
            raise UsersStoreUnavailableError('Could not list Users discovery directory') from error
        by_id: dict[str, DiscoveredUser] = {}
        for blob in sorted(blobs, key=lambda item: item.name):
            name = blob.name
            leaf = name.removeprefix(base)
            if not name.startswith(base) or '/' in leaf or not leaf.endswith('.json'):
                raise UsersDefinitionError('Users discovery directory contains an invalid filename')
            if blob.size > _MAX_DOCUMENT_BYTES:
                raise UsersDefinitionError('Users discovery document exceeds the size limit')
            try:
                raw = self._client.download(container_name=self._container_name, blob_name=name)
            except StorageError as error:
                raise UsersStoreUnavailableError('Could not read Users discovery document') from error
            if len(raw) > _MAX_DOCUMENT_BYTES:
                raise UsersDefinitionError('Users discovery document exceeds the size limit')
            user = _parse_document(raw)
            if leaf != f'{user.user_id}.json':
                raise UsersDefinitionError('Users discovery filename does not match identity')
            if user.user_id in by_id:
                raise UsersDefinitionError('Users discovery contains duplicate identities')
            by_id[user.user_id] = user
        return tuple(by_id[key] for key in sorted(by_id))


def _parse_document(raw: bytes) -> DiscoveredUser:
    try:
        document = json.loads(raw.decode('utf-8'))
        if not isinstance(document, dict):
            raise TypeError
        # El contrato explícito evita aceptar archivos ajenos como identidades.
        if document.get('document_type') != _DOCUMENT_TYPE or document.get('schema_version') != _SCHEMA_VERSION:
            raise ValueError
        if set(document) - {'document_type', 'schema_version', 'issuer', 'subject_id', 'display_name', 'email'}:
            raise ValueError
        issuer = document['issuer']
        subject_id = document['subject_id']
        display_name = document.get('display_name')
        email = document.get('email')
        if not isinstance(issuer, str) or not isinstance(subject_id, str):
            raise TypeError
        if display_name is not None and not isinstance(display_name, str):
            raise TypeError
        if email is not None and not isinstance(email, str):
            raise TypeError
        user = DiscoveredUser(
            issuer=issuer, subject_id=subject_id, display_name=display_name, email=email
        )
        if user.display_name is None and user.email is None:
            raise ValueError
        return user
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise UsersDefinitionError('Users discovery document is invalid') from error
