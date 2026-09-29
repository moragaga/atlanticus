from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace

import pytest

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.enums import ToolConfigurationKind
from ada.web.tools.projection.cosmos import TOOL_PROJECTION_STORAGE_RESOURCE
from ada_command_center.tools.discovery_cosmos.connections import (
    ToolCosmosConnectionConfigurationError,
)
from atlanticus.connectivity.cosmos import CosmosSettings

qualify = import_module('qualify')


def _reader(*, same_database: bool = False):
    process = CosmosSettings(
        endpoint='https://localhost:8081', database_name='validation_process', key='testing'
    )
    integrated = CosmosSettings(
        endpoint='https://localhost:8081',
        database_name='validation_process' if same_database else 'validation_integrated',
        key='testing',
    )
    return SimpleNamespace(
        external=lambda: {'process': process, 'integrated': integrated},
        storage=lambda: {
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'validation',
        },
        manager_provider='local',
    )


def test_both_external_fixtures_validate_with_existing_ada_contracts() -> None:
    result = qualify.validate_fixtures()
    assert result == {
        'status': 'VALID',
        'tools': ['validation_process', 'validation_integrated'],
    }
    assert qualify.fixture('process').kind is ToolConfigurationKind.PROCESS
    assert qualify.fixture('integrated').kind is ToolConfigurationKind.INTEGRATED_OPERATIONS


def test_projections_use_existing_namespaces_and_cosmos_topology() -> None:
    expected = {
        'process': 'conciencia_situacional/validation_process',
        'integrated': 'conciencia_situacional/validation_integrated',
    }
    for name, (_, namespace) in qualify._TOOLS.items():
        assert (
            AdaStorageNamespace('conciencia_situacional', namespace).tool_prefix == expected[name]
        )
    contract = TOOL_PROJECTION_STORAGE_RESOURCE
    assert qualify._spec(contract).name == contract.default_physical_name
    assert qualify._spec(contract).partition_key_path == '/partition_key'


def test_preflight_rejects_shared_tool_cosmos_database() -> None:
    with pytest.raises(qualify.QualificationError, match='separate Cosmos databases'):
        qualify.preflight(_reader(same_database=True))


def test_preflight_accepts_distinct_connections_without_mutating_resources() -> None:
    result = qualify.preflight(_reader())
    assert result['status'] == 'READY'
    assert result['connections'] == ['integrated', 'process']


def test_inspect_cannot_qualify_a_partial_initial_discovery(monkeypatch) -> None:
    @contextmanager
    def catalog(_reader):
        yield SimpleNamespace(get_current=lambda: None)

    class DiscoveryStub:
        def __init__(self, **kwargs):
            pass

        def inspect(self):
            return SimpleNamespace(
                can_confirm=True,
                current_revision=None,
                issue=None,
                connections=(
                    SimpleNamespace(
                        connection_name='process',
                        status='READY',
                        tools=(SimpleNamespace(tool_key='validation_process'),),
                    ),
                    SimpleNamespace(connection_name='integrated', status='NO_TOOLS', tools=()),
                ),
            )

    monkeypatch.setattr(qualify, '_catalog', catalog)
    monkeypatch.setattr(qualify, 'ToolCatalogManagerService', DiscoveryStub)
    result = qualify.inspect_catalog(_reader())
    assert result['status'] == 'BLOCKED'
    assert result['can_confirm'] is False


def test_configuration_error_identifies_manager_env_without_exposing_values(
    monkeypatch, capsys
) -> None:
    import sys

    def no_connections():
        raise ToolCosmosConnectionConfigurationError('No external Tool Cosmos connections declared')

    monkeypatch.setattr(qualify, '_reader', no_connections)
    monkeypatch.setattr(sys, 'argv', ['qualify.py', 'preflight'])
    assert qualify.main() == 2
    result = __import__('json').loads(capsys.readouterr().out)
    assert result['error_type'] == 'ToolCosmosConnectionConfigurationError'
    assert result['issue'] == 'No external Tool Cosmos connections declared'
    assert result['configuration_source'].endswith('ada-command-center-configuration-manager/.env')
    assert '.env.detail is documentation only' in result['hint']
