from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from application.master_projection import reader as module


def test_reader_with_no_material_is_safe():
    reader = module.StarterMasterMaterialReader(None)
    assert reader.inspect() == 'ABSENT'
    assert reader.fingerprint() is None
    with pytest.raises(RuntimeError, match='not configured'):
        reader.unlock(
            service_user='root', password='not-important',
            application_namespace='app', environment='local',
        )


def test_reader_rejects_relative_path():
    with pytest.raises(ValueError, match='absolute'):
        module.StarterMasterMaterialReader(module.Path('relative.zip'))


def test_reader_delegates_only_to_master_material(tmp_path, monkeypatch):
    archive = tmp_path / 'protected.zip'
    archive.write_bytes(b'encrypted-archive-placeholder')
    monkeypatch.setattr(module, 'inspect_master_material', lambda _: 'PRESENT')
    reader = module.StarterMasterMaterialReader(archive)
    assert reader.inspect() == 'PRESENT'
    assert reader.fingerprint() == hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.write_bytes(b'new-encrypted-archive-placeholder')
    assert reader.fingerprint() == hashlib.sha256(archive.read_bytes()).hexdigest()
    invoked = []

    def unlock(path, **kwargs):
        invoked.append((path, kwargs))
        return SimpleNamespace(material_id='restricted-to-master')

    monkeypatch.setattr(module, 'unlock_master_material', unlock)
    result = reader.unlock(
        service_user='master', password='not-logged',
        application_namespace='app', environment='local',
    )
    assert result.material_id == 'restricted-to-master'
    assert invoked == [(archive, {
        'service_user': 'master', 'password': 'not-logged',
        'application_namespace': 'app', 'environment': 'local',
    })]


def test_fingerprint_refuses_oversized_or_invalid_material(tmp_path, monkeypatch):
    archive = tmp_path / 'material.zip'
    archive.write_bytes(b'x' * 24577)
    monkeypatch.setattr(module, 'inspect_master_material', lambda _: 'PRESENT')
    reader = module.StarterMasterMaterialReader(archive)
    assert reader.fingerprint() is None
    monkeypatch.setattr(module, 'inspect_master_material', lambda _: 'INVALID')
    assert reader.fingerprint() is None
