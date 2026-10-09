from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageClient,
    StorageConflictError,
    StorageError,
)


class DeploymentAccessStorageError(RuntimeError):
    pass


class DeploymentAccessConflictError(DeploymentAccessStorageError):
    pass


@runtime_checkable
class DeploymentAccessStorage(Protocol):
    def read(self) -> bytes | None: ...

    def write(self, content: bytes, *, overwrite: bool) -> None: ...

    def delete(self) -> None: ...


class BlobDeploymentAccessStorage:
    def __init__(self, *, client: StorageClient, container_name: str, blob_name: str) -> None:
        if not isinstance(client, StorageClient):
            raise TypeError('Deployment access Blob storage requires StorageClient')
        if not isinstance(container_name, str) or not container_name.strip():
            raise ValueError('Deployment access Blob container is required')
        if not isinstance(blob_name, str) or not blob_name.strip():
            raise ValueError('Deployment access Blob name is required')
        self._client = client
        self._container_name = container_name
        self._blob_name = blob_name

    def read(self) -> bytes | None:
        try:
            return self._client.download(
                container_name=self._container_name, blob_name=self._blob_name
            )
        except StorageBlobNotFoundError:
            return None
        except StorageError as error:
            raise DeploymentAccessStorageError(
                'Deployment access storage is unavailable'
            ) from error

    def write(self, content: bytes, *, overwrite: bool) -> None:
        try:
            self._client.upload(
                container_name=self._container_name,
                blob_name=self._blob_name,
                data=content,
                overwrite=overwrite,
                content_type='application/zip',
            )
        except StorageConflictError as error:
            raise DeploymentAccessConflictError(
                'Deployment access material already exists'
            ) from error
        except StorageError as error:
            raise DeploymentAccessStorageError(
                'Could not save deployment access material'
            ) from error

    def delete(self) -> None:
        try:
            self._client.delete(container_name=self._container_name, blob_name=self._blob_name)
        except StorageBlobNotFoundError as error:
            raise DeploymentAccessConflictError(
                'Deployment access material does not exist'
            ) from error
        except StorageError as error:
            raise DeploymentAccessStorageError(
                'Could not delete deployment access material'
            ) from error


class LocalDeploymentAccessStorage:
    def __init__(self, path: Path) -> None:
        path = Path(path)
        if not path.is_absolute():
            raise ValueError('Deployment access material path must be absolute')
        self._path = path

    def read(self) -> bytes | None:
        try:
            if self._path.is_symlink():
                raise DeploymentAccessStorageError('Deployment access material path is invalid')
            with self._path.open('rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise DeploymentAccessStorageError('Deployment access material path is invalid')
                return stream.read(24577)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise DeploymentAccessStorageError(
                'Could not read deployment access material'
            ) from error

    def write(self, content: bytes, *, overwrite: bool) -> None:
        if not self._path.parent.is_dir() or self._path.is_symlink():
            raise DeploymentAccessStorageError('Deployment access material destination is invalid')
        descriptor, name = tempfile.mkstemp(
            dir=self._path.parent, prefix=f'.{self._path.name}.', suffix='.tmp'
        )
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o600)
            if overwrite:
                if self._path.is_symlink():
                    raise DeploymentAccessStorageError(
                        'Deployment access material destination is invalid'
                    )
                os.replace(name, self._path)
            else:
                try:
                    os.link(name, self._path)
                except FileExistsError as error:
                    raise DeploymentAccessConflictError(
                        'Deployment access material already exists'
                    ) from error
        except OSError as error:
            raise DeploymentAccessStorageError(
                'Could not save deployment access material'
            ) from error
        finally:
            Path(name).unlink(missing_ok=True)

    def delete(self) -> None:
        if self._path.is_symlink():
            raise DeploymentAccessStorageError('Deployment access material path is invalid')
        try:
            self._path.unlink()
        except FileNotFoundError as error:
            raise DeploymentAccessConflictError(
                'Deployment access material does not exist'
            ) from error
        except OSError as error:
            raise DeploymentAccessStorageError(
                'Could not delete deployment access material'
            ) from error
