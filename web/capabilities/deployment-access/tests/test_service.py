from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from atlanticus.web.deployment_access import (
    DeploymentAccessConflictError,
    DeploymentAccessService,
    DeploymentAccessStorageError,
    DeploymentAccessVerificationError,
    MaterialAvailability,
    service as implementation,
)
from atlanticus.web.deployment_access.material import DeploymentAccessIdentity


@dataclass
class InMemoryStorage:
    content: bytes | None = None
    unavailable: bool = False
    persist: bool = True

    def read(self) -> bytes | None:
        if self.unavailable:
            raise DeploymentAccessStorageError('Unavailable')
        return self.content

    def write(self, content: bytes, *, overwrite: bool) -> None:
        if self.content is not None and not overwrite:
            raise DeploymentAccessConflictError('Exists')
        if self.persist:
            self.content = content

    def delete(self) -> None:
        if self.content is None:
            raise DeploymentAccessConflictError('Missing')
        if self.persist:
            self.content = None


def _service(storage: InMemoryStorage) -> DeploymentAccessService:
    return DeploymentAccessService(
        storage=storage, application_namespace='example', environment='qa'
    )


def _fake_material(monkeypatch) -> DeploymentAccessIdentity:
    identity = DeploymentAccessIdentity('x' * 32, 'operator', 'example', 'qa')
    monkeypatch.setattr(implementation, 'generate_material', lambda **_: (b'protected', identity))
    monkeypatch.setattr(
        implementation,
        'inspect_material',
        lambda content: (
            MaterialAvailability.PRESENT
            if content == b'protected'
            else MaterialAvailability.INVALID
        ),
    )
    monkeypatch.setattr(implementation, 'unlock_material', lambda content, **_: identity)
    return identity


def test_inspection_distinguishes_absent_invalid_present_and_unavailable(monkeypatch) -> None:
    _fake_material(monkeypatch)
    storage = InMemoryStorage()
    service = _service(storage)
    assert service.inspect().availability is MaterialAvailability.ABSENT
    storage.content = b'invalid'
    assert service.inspect().availability is MaterialAvailability.INVALID
    storage.content = b'protected'
    status = service.inspect()
    assert status.availability is MaterialAvailability.PRESENT
    assert status.fingerprint == hashlib.sha256(b'protected').hexdigest()
    storage.unavailable = True
    assert service.inspect().availability is MaterialAvailability.UNAVAILABLE
    assert service.inspect().fingerprint is None


def test_bootstrap_is_exclusive_and_rotation_overwrites(monkeypatch) -> None:
    identity = _fake_material(monkeypatch)
    storage = InMemoryStorage()
    service = _service(storage)
    assert service.bootstrap_initial(service_user='operator', password='long-password') == identity
    with pytest.raises(DeploymentAccessConflictError):
        service.bootstrap_initial(service_user='operator', password='long-password')
    storage.content = b'old'
    assert service.create_or_replace(service_user='operator', password='long-password') == identity
    assert storage.content == b'protected'
    result = service.authenticate(service_user='operator', password='long-password')
    assert result.identity == identity
    assert result.fingerprint == hashlib.sha256(b'protected').hexdigest()


def test_save_and_delete_must_verify_durable_result(monkeypatch) -> None:
    _fake_material(monkeypatch)
    storage = InMemoryStorage(persist=False)
    service = _service(storage)
    with pytest.raises(DeploymentAccessVerificationError, match='write'):
        service.create_or_replace(service_user='operator', password='long-password')
    storage.content = b'protected'
    with pytest.raises(DeploymentAccessVerificationError, match='deletion'):
        service.delete()
    storage.persist = True
    service.delete()
    assert service.inspect().availability is MaterialAvailability.ABSENT
