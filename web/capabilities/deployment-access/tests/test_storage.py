from __future__ import annotations

import os

import pytest

from atlanticus.web.deployment_access import (
    DeploymentAccessConflictError,
    DeploymentAccessStorageError,
    LocalDeploymentAccessStorage,
)


def test_local_storage_is_private_and_supports_initial_write_rotation_and_deletion(
    tmp_path,
) -> None:
    path = tmp_path / 'access.zip'
    store = LocalDeploymentAccessStorage(path)
    assert store.read() is None
    store.write(b'first', overwrite=False)
    assert store.read() == b'first'
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(DeploymentAccessConflictError):
        store.write(b'not-allowed', overwrite=False)
    assert store.read() == b'first'
    store.write(b'replaced', overwrite=True)
    assert store.read() == b'replaced'
    store.delete()
    assert store.read() is None
    with pytest.raises(DeploymentAccessConflictError):
        store.delete()


def test_local_storage_refuses_symlinks(tmp_path) -> None:
    target = tmp_path / 'target'
    target.write_bytes(b'original')
    link = tmp_path / 'link'
    link.symlink_to(target)
    store = LocalDeploymentAccessStorage(link)
    with pytest.raises(DeploymentAccessStorageError):
        store.read()
    with pytest.raises(DeploymentAccessStorageError):
        store.write(b'anything', overwrite=True)
    with pytest.raises(DeploymentAccessStorageError):
        store.delete()
    assert target.read_bytes() == b'original'
