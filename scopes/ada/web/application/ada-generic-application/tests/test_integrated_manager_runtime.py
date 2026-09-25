from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_dependencies,
)
from ada.web.application.generic import bootstrap
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.tools.persistence import ToolProjectionResolutionState


def _settings(tmp_path) -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'test_tool',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )


def _local_manager(tmp_path):
    return create_local_configuration_manager_dependencies(source_root=tmp_path / 'manager-source')


def test_manager_and_operational_surfaces_share_one_runtime_without_a_tool(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_dependencies=_local_manager(tmp_path),
    )
    client = runtime.server.test_client()
    assert runtime.dash.server is runtime.server
    assert client.get('/health/live').status_code == 200
    assert client.get('/').status_code == 200
    assert client.get('/manager').status_code == 200
    assert client.get('/manager/users').status_code == 200

    layout_response = client.get('/_dash-layout')
    assert layout_response.status_code == 200
    layout = json.dumps(layout_response.get_json(), ensure_ascii=False)
    assert 'ada-operational-surface' in layout
    assert 'ada-manager-surface' in layout
    assert 'atlanticus-manager-location' in layout
    assert 'ada-navigation-offcanvas' in layout
    assert 'atlanticus-manager-sidebar' in layout

    registered = set(runtime.page_modules)
    assert 'ada.web.application.generic.pages.home' in registered
    assert 'ada.web.application.configuration_manager.pages.manager' in registered
    assert 'ada.web.application.configuration_manager.pages.module' in registered
    callback_keys = tuple(runtime.dash.callback_map)
    assert any('ada-manager-surface.hidden' in key for key in callback_keys)
    assert any('atlanticus-manager-content.children' in key for key in callback_keys)


def test_manager_mount_is_independent_of_tool_ready_state(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    monkeypatch.setattr(
        bootstrap,
        '_resolve_tool_projection',
        lambda _settings: SimpleNamespace(
            state=ToolProjectionResolutionState.READY,
            projection=object(),
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        'create_definition_from_tool_resolution',
        lambda _resolution: create_application_definition(),
    )

    runtime = bootstrap.create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_dependencies=_local_manager(tmp_path),
    )
    assert runtime.server.test_client().get('/manager').status_code == 200
    assert any(
        module_name.endswith('configuration_manager.pages.manager')
        for module_name in runtime.page_modules
    )


def test_invalid_manager_dependencies_fail_before_tool_initialization(tmp_path) -> None:
    with pytest.raises(TypeError, match='manager_dependencies'):
        bootstrap.create_operational_application_runtime(
            settings=_settings(tmp_path),
            manager_dependencies=object(),
        )


def test_manager_is_not_implicitly_enabled_by_local_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = bootstrap.create_operational_application_runtime(settings=_settings(tmp_path))
    assert all('configuration_manager.pages' not in name for name in runtime.page_modules)
    assert runtime.server.test_client().get('/health/live').status_code == 200
