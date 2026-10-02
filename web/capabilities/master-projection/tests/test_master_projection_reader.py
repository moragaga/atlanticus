from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.master_projection import reader as module


def test_local_reader_reports_absent_canonical_file(tmp_path):
    reader = module.LocalMasterMaterialReader((tmp_path / 'material.zip').resolve())
    assert reader.inspect() == 'ABSENT'
    assert reader.fingerprint() is None


def test_local_reader_rejects_relative_path():
    with pytest.raises(ValueError, match='absolute'):
        module.LocalMasterMaterialReader(Path('relative.zip'))


def test_local_reader_delegates_unlock_and_tracks_current_fingerprint(tmp_path, monkeypatch):
    archive = (tmp_path / 'protected.zip').resolve()
    archive.write_bytes(b'encrypted-archive-placeholder')
    monkeypatch.setattr(module, 'inspect_master_material', lambda _: 'PRESENT')
    reader = module.LocalMasterMaterialReader(archive)
    assert reader.inspect() == 'PRESENT'
    assert reader.fingerprint() == hashlib.sha256(archive.read_bytes()).hexdigest()
    invoked = []

    def unlock(path, **kwargs):
        invoked.append((path, kwargs))
        return SimpleNamespace(material_id='restricted-to-master')

    monkeypatch.setattr(module, 'unlock_master_material', unlock)
    result = reader.unlock(
        service_user='master',
        password='not-logged',
        application_namespace='app',
        environment='local',
    )
    assert result.material_id == 'restricted-to-master'
    assert invoked == [
        (
            archive,
            {
                'service_user': 'master',
                'password': 'not-logged',
                'application_namespace': 'app',
                'environment': 'local',
            },
        )
    ]


def test_blob_reader_uses_canonical_remote_content_without_local_path(monkeypatch):
    client = object.__new__(StorageClient)
    reader = module.BlobMasterMaterialReader(
        client=client,
        container_name='configuration',
        blob_name='app/master-projection/material.zip',
    )
    content = b'encrypted-archive-placeholder'
    monkeypatch.setattr(reader, '_download', lambda: content)
    monkeypatch.setattr(module, '_inspect_content', lambda _: 'PRESENT')
    assert reader.inspect() == 'PRESENT'
    assert reader.fingerprint() == hashlib.sha256(content).hexdigest()


def test_blob_reader_absent_material_is_safe(monkeypatch):
    client = object.__new__(StorageClient)
    reader = module.BlobMasterMaterialReader(
        client=client,
        container_name='configuration',
        blob_name='app/master-projection/material.zip',
    )
    monkeypatch.setattr(reader, '_download', lambda: None)
    assert reader.inspect() == 'ABSENT'
    assert reader.fingerprint() is None
    with pytest.raises(RuntimeError, match='absent'):
        reader.unlock(
            service_user='master',
            password='not-important',
            application_namespace='app',
            environment='local',
        )
