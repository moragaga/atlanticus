from __future__ import annotations

import pytest

from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageConflictError,
    StorageError,
)
from atlanticus.web.deployment_access import (
    BlobDeploymentAccessStorage,
    DeploymentAccessConflictError,
    DeploymentAccessStorageError,
    storage as implementation,
)


class FakeStorageClient:
    def __init__(self) -> None:
        self.content: bytes | None = None
        self.unavailable = False
        self.uploads: list[dict[str, object]] = []

    def download(self, *, container_name: str, blob_name: str) -> bytes:
        if self.unavailable:
            raise StorageError('Unavailable')
        if self.content is None:
            raise StorageBlobNotFoundError('Missing')
        return self.content

    def upload(self, **kwargs) -> None:
        self.uploads.append(kwargs)
        if kwargs['overwrite'] is False and self.content is not None:
            raise StorageConflictError('Conflict')
        self.content = kwargs['data']

    def delete(self, **kwargs) -> None:
        if self.content is None:
            raise StorageBlobNotFoundError('Missing')
        self.content = None


def test_blob_storage_uses_configured_destination_and_explicit_overwrite(monkeypatch) -> None:
    monkeypatch.setattr(implementation, 'StorageClient', FakeStorageClient)
    client = FakeStorageClient()
    storage = BlobDeploymentAccessStorage(
        client=client, container_name='configured-container', blob_name='manager/access.zip'
    )
    assert storage.read() is None
    storage.write(b'initial', overwrite=False)
    with pytest.raises(DeploymentAccessConflictError):
        storage.write(b'conflict', overwrite=False)
    storage.write(b'replacement', overwrite=True)
    assert storage.read() == b'replacement'
    assert client.uploads[-1] == {
        'container_name': 'configured-container',
        'blob_name': 'manager/access.zip',
        'data': b'replacement',
        'overwrite': True,
        'content_type': 'application/zip',
    }
    storage.delete()
    assert storage.read() is None


def test_storage_unavailability_is_not_reported_as_absence(monkeypatch) -> None:
    monkeypatch.setattr(implementation, 'StorageClient', FakeStorageClient)
    client = FakeStorageClient()
    client.unavailable = True
    storage = BlobDeploymentAccessStorage(
        client=client, container_name='container', blob_name='access.zip'
    )
    with pytest.raises(DeploymentAccessStorageError, match='unavailable'):
        storage.read()
    with pytest.raises(DeploymentAccessConflictError, match='does not exist'):
        storage.delete()
