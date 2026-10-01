from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from application.master_projection import provision
from ada.web.application.generic.settings import AdaGenericSettings


def _identity():
    return SimpleNamespace(material_id='material-one')


def test_local_provision_uses_canonical_settings_path(tmp_path, monkeypatch):
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_APPLICATION_NAMESPACE': 'app',
            'ADA_TOOL_NAMESPACE': 'tool',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )
    captured = {}

    def generate(path, **kwargs):
        captured['path'] = path
        captured.update(kwargs)
        path.write_bytes(b'material')
        return _identity()

    monkeypatch.setattr(provision, 'generate_master_material', generate)
    result = provision._generate_local(settings, service_user='master', password='secret-password')

    assert captured['path'] == tmp_path / 'app/master-projection/material.zip'
    assert captured['application_namespace'] == 'app'
    assert captured['environment'] == 'local'
    assert result['persistence'] == 'local'
    assert result['location'] == str(captured['path'])


def test_durable_provision_uploads_to_canonical_blob(tmp_path, monkeypatch):
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_PERSISTENCE_MODE': 'durable',
            'ADA_APPLICATION_NAMESPACE': 'app',
            'ADA_TOOL_NAMESPACE': 'tool',
            'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
            'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'http://localhost:8081',
            'ADA_TOOL_PROJECTION_COSMOS_KEY': 'test-only',
            'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'ada',
        }
    )
    captured = {}

    def generate(path: Path, **kwargs):
        path.write_bytes(b'material')
        return _identity()

    class Storage:
        def __init__(self, *, settings):
            captured['settings'] = settings

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def upload(self, **kwargs):
            captured['upload'] = kwargs

    monkeypatch.setattr(provision, 'generate_master_material', generate)
    monkeypatch.setattr(provision, 'StorageClient', Storage)
    result = provision._generate_durable(
        settings, service_user='master', password='secret-password'
    )

    assert captured['upload']['container_name'] == 'configuration'
    assert captured['upload']['blob_name'] == 'app/master-projection/material.zip'
    assert captured['upload']['data'] == b'material'
    assert captured['upload']['overwrite'] is False
    assert result['persistence'] == 'durable'
    assert result['location'] == 'blob://configuration/app/master-projection/material.zip'
