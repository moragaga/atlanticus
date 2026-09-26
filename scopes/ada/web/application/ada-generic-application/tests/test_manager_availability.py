from __future__ import annotations

import json
from dataclasses import replace

import pytest
from dash import dcc, html

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_dependencies,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.manager_integration import (
    MANAGER_SURFACE_ID,
    MANAGER_UNAVAILABLE_ID,
    OPERATIONAL_SURFACE_ID,
    integrate_manager_surface,
)
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.connectivity.cosmos import CosmosOperationError
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.errors import UsersStoreUnavailableError

_LOCATION_ID = 'availability-test-location'


class UnavailableManagerStub:
    @property
    def web_modules(self):
        return (WebModule(name='availability-manager'),)

    def layout(self, _services):
        raise CosmosOperationError('secret-value-must-not-be-exposed')


class InvalidManagerStub(UnavailableManagerStub):
    def layout(self, _services):
        raise ValueError('Manager composition is invalid')


def _definition(tmp_path):
    return WebApplicationDefinition(
        import_name='ada.web.application.generic',
        metadata=ApplicationMetadata('ada-generic-application', 'ADA', '0.2.17'),
        publications_root=tmp_path / 'publications',
        layout=lambda _services: html.Div(id='operational-contract'),
        modules=(WebModule(name='availability-operational'),),
        page_packages=('ada.web.application.generic.pages',),
    )


def _integrated(tmp_path, *, manager, unavailable_errors):
    return integrate_manager_surface(
        _definition(tmp_path),
        manager=manager,
        page_packages=('ada.web.application.configuration_manager.pages',),
        route_prefix='/manager',
        location_id=_LOCATION_ID,
        unavailable_errors=unavailable_errors,
    )


def test_unavailable_manager_does_not_prevent_operational_layout(tmp_path, caplog):
    definition = _integrated(
        tmp_path,
        manager=UnavailableManagerStub(),
        unavailable_errors=(CosmosOperationError,),
    )

    with caplog.at_level('WARNING'):
        layout = definition.layout(ServiceRegistry())

    assert layout.children[0].id == OPERATIONAL_SURFACE_ID
    assert layout.children[0].children.id == 'operational-contract'
    assert layout.children[1].id == MANAGER_SURFACE_ID
    fallback = layout.children[1].children
    assert fallback.id == MANAGER_UNAVAILABLE_ID
    assert isinstance(fallback.children[0], dcc.Location)
    assert fallback.children[0].id == _LOCATION_ID
    assert fallback.role == 'alert'
    assert 'Manager presentation unavailable (CosmosOperationError)' in caplog.text
    assert 'secret-value-must-not-be-exposed' not in caplog.text


def test_unavailable_manager_error_contract_must_be_explicit(tmp_path):
    definition = _integrated(
        tmp_path,
        manager=UnavailableManagerStub(),
        unavailable_errors=(),
    )

    with pytest.raises(CosmosOperationError):
        definition.layout(ServiceRegistry())


def test_programming_errors_remain_visible(tmp_path):
    definition = _integrated(
        tmp_path,
        manager=InvalidManagerStub(),
        unavailable_errors=(CosmosOperationError,),
    )

    with pytest.raises(ValueError, match='composition is invalid'):
        definition.layout(ServiceRegistry())


def test_recoverable_exception_types_are_validated(tmp_path):
    with pytest.raises(TypeError, match='exception types'):
        _integrated(
            tmp_path,
            manager=UnavailableManagerStub(),
            unavailable_errors=(CosmosOperationError, 'invalid'),
        )


def test_real_runtime_keeps_operational_shell_with_unavailable_manager(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'test_tool',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )
    dependencies = create_local_configuration_manager_dependencies(
        source_root=tmp_path / 'manager-source'
    )

    def manager_principal_unavailable():
        raise UsersStoreUnavailableError('private-provider-detail')

    dependencies = replace(dependencies, principal_provider=manager_principal_unavailable)
    runtime = bootstrap.create_operational_application_runtime(
        settings=settings,
        manager_dependencies=dependencies,
    )
    client = runtime.server.test_client()
    with caplog.at_level('WARNING'):
        response = client.get('/_dash-layout')
    assert response.status_code == 200
    payload = json.dumps(response.get_json(), ensure_ascii=False)
    assert 'ada-operational-header' in payload or 'ada-operational-surface' in payload
    assert MANAGER_UNAVAILABLE_ID in payload
    assert 'private-provider-detail' not in payload
    assert 'private-provider-detail' not in caplog.text
    assert client.get('/').status_code == 200
    assert client.get('/manager', headers={'Accept': 'text/html'}).status_code == 403
