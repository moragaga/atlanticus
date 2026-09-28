from __future__ import annotations

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.local import LocalIdentityProvider


class TrackingLocalIdentityProvider(LocalIdentityProvider):
    def __init__(self, *, reject: bool = False) -> None:
        super().__init__(subject_id='local:jane-doe')
        self.reject = reject
        self.calls = 0

    def resolve(self, request):
        self.calls += 1
        if self.reject:
            raise IdentityAuthenticationError('Invalid test identity')
        return super().resolve(request)


class FakeMasterMaterialReader:
    def __init__(self, status: str) -> None:
        self.status = status

    def inspect(self) -> str:
        return self.status

    def fingerprint(self) -> str | None:
        return 'a' * 64 if self.status == 'PRESENT' else None

    def unlock(self, **kwargs):
        raise AssertionError('Unprivileged page access must not unlock Master material')


@pytest.mark.parametrize(
    ('status', 'expected'),
    [
        ('ABSENT', 'No existe acceso Master Projection configurado'),
        ('PRESENT', 'Usuario de servicio'),
    ],
)
def test_integrated_master_route_does_not_require_manager_access_snapshot(
    tmp_path, monkeypatch, status, expected
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'test_tool',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )
    identity_provider = TrackingLocalIdentityProvider()
    runtime = create_operational_application_runtime(
        settings=settings,
        manager_stores=create_local_configuration_manager_stores(
            source_root=tmp_path / 'sources',
        ),
        identity_provider=identity_provider,
        master_material_reader=FakeMasterMaterialReader(status),
    )
    client = runtime.server.test_client()
    html_headers = {'Accept': 'text/html'}

    master_page = client.get('/master-projection', headers=html_headers)
    assert master_page.status_code == 200
    assert expected in master_page.get_data(as_text=True)
    assert master_page.headers['Cache-Control'] == 'no-store, private'

    assert identity_provider.calls == 0
    other_route = client.get('/master-projection/unknown', headers=html_headers)
    assert other_route.status_code != 500
    assert identity_provider.calls == 1
    assert client.get('/master-projection/logout', headers=html_headers).status_code == 405
    assert identity_provider.calls == 1
    assert client.get('/manager', headers=html_headers).status_code == 200
    assert identity_provider.calls == 2


def test_unrecognized_master_path_does_not_bypass_application_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'test_tool',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )
    identity_provider = TrackingLocalIdentityProvider(reject=True)
    runtime = create_operational_application_runtime(
        settings=settings,
        manager_stores=create_local_configuration_manager_stores(
            source_root=tmp_path / 'sources',
        ),
        identity_provider=identity_provider,
        master_material_reader=FakeMasterMaterialReader('PRESENT'),
    )
    client = runtime.server.test_client()
    html_headers = {'Accept': 'text/html'}

    assert client.get('/master-projection', headers=html_headers).status_code == 200
    assert identity_provider.calls == 0
    assert client.get('/master-projection/logout', headers=html_headers).status_code == 405
    assert identity_provider.calls == 0
    assert client.get('/master-projection/unknown', headers=html_headers).status_code == 401
    assert identity_provider.calls == 1
    assert client.get('/manager', headers=html_headers).status_code == 401
    assert identity_provider.calls == 2
