from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ada.web.application.generic.master_projection.material import (
    MasterMaterialIdentity,
    inspect_master_material,
    unlock_master_material,
)
from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageClient,
    StorageError,
)

_ARCHIVE_LIMIT = 24576


@contextmanager
def _material_file(content: bytes):
    descriptor, name = tempfile.mkstemp(prefix='.master-projection-', suffix='.zip')
    path = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        os.chmod(path, 0o600)
        yield path
    finally:
        path.unlink(missing_ok=True)


def _inspect_content(content: bytes) -> str:
    if not content or len(content) > _ARCHIVE_LIMIT:
        return 'INVALID'
    with _material_file(content) as path:
        return str(inspect_master_material(path))


class LocalMasterMaterialReader:
    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError('Master Projection material path must be absolute')
        self._path = path

    def inspect(self) -> str:
        return str(inspect_master_material(self._path))

    def fingerprint(self) -> str | None:
        if self.inspect() != 'PRESENT':
            return None
        try:
            with self._path.open('rb') as source:
                content = source.read(_ARCHIVE_LIMIT + 1)
            if not content or len(content) > _ARCHIVE_LIMIT:
                return None
            return hashlib.sha256(content).hexdigest()
        except OSError:
            return None

    def unlock(
        self,
        *,
        service_user: str,
        password: str,
        application_namespace: str,
        environment: str,
    ) -> MasterMaterialIdentity:
        return unlock_master_material(
            self._path,
            service_user=service_user,
            password=password,
            application_namespace=application_namespace,
            environment=environment,
        )


class BlobMasterMaterialReader:
    def __init__(
        self,
        *,
        client: StorageClient,
        container_name: str,
        blob_name: str,
    ) -> None:
        if not isinstance(client, StorageClient):
            raise TypeError('Master Projection Blob reader requires StorageClient')
        if not isinstance(container_name, str) or not container_name.strip():
            raise ValueError('Master Projection Blob container name is required')
        if not isinstance(blob_name, str) or not blob_name.strip():
            raise ValueError('Master Projection Blob name is required')
        self._client = client
        self._container_name = container_name
        self._blob_name = blob_name

    def _download(self) -> bytes | None:
        try:
            return self._client.download(
                container_name=self._container_name,
                blob_name=self._blob_name,
            )
        except StorageBlobNotFoundError:
            return None

    def inspect(self) -> str:
        try:
            content = self._download()
        except StorageError:
            return 'INVALID'
        if content is None:
            return 'ABSENT'
        return _inspect_content(content)

    def fingerprint(self) -> str | None:
        try:
            content = self._download()
        except StorageError:
            return None
        if content is None or _inspect_content(content) != 'PRESENT':
            return None
        return hashlib.sha256(content).hexdigest()

    def unlock(
        self,
        *,
        service_user: str,
        password: str,
        application_namespace: str,
        environment: str,
    ) -> MasterMaterialIdentity:
        try:
            content = self._download()
        except StorageError as error:
            raise RuntimeError('Master Projection material is unavailable') from error
        if content is None:
            raise RuntimeError('Master Projection material is absent')
        with _material_file(content) as path:
            return unlock_master_material(
                path,
                service_user=service_user,
                password=password,
                application_namespace=application_namespace,
                environment=environment,
            )
