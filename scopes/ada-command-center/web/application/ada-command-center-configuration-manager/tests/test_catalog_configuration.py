from __future__ import annotations

import pytest

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    CommandCenterConfigurationError,
    ManagerConfigurationReader,
)
from atlanticus.web.configuration import WebEnvironment


def _local(root, *, environ=None):
    return ManagerConfigurationReader(root=root, environ_supplier=lambda: environ or {})


def test_local_env_groups_external_connections_without_index(tmp_path) -> None:
    (tmp_path / '.env').write_text(
        'ATLANTICUS_ENVIRONMENT=local\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT=https://mina.example.com\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_DATABASE_NAME=mine\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY=secret-mine\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_PLANTA_ENDPOINT=https://planta.example.com\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_PLANTA_DATABASE_NAME=plant\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_PLANTA_KEY=secret-plant\n'
    )
    reader = _local(tmp_path)
    resolved = reader.external()
    assert reader.environment is WebEnvironment.LOCAL
    assert set(resolved) == {'mina', 'planta'}
    assert resolved['mina'].database_name == 'mine'
    assert 'secret-mine' not in repr(resolved)


def test_process_values_override_local_env(tmp_path) -> None:
    (tmp_path / '.env').write_text(
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT=https://mina.example.com\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_DATABASE_NAME=mine\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY=old\n'
    )
    reader = _local(tmp_path, environ={'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY': 'new'})
    assert reader.external()['mina'].key == 'new'


def test_production_must_be_selected_by_host_not_local_file(tmp_path) -> None:
    (tmp_path / '.env').write_text('ATLANTICUS_ENVIRONMENT=production\n')
    with pytest.raises(CommandCenterConfigurationError, match='explicitly supplied'):
        _local(tmp_path)


def test_production_uses_pre_resolved_host_values_without_manifest(tmp_path) -> None:
    (tmp_path / '.env').write_text(
        'ATLANTICUS_ENVIRONMENT=local\n'
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY=untrusted-local-value\n'
    )
    (tmp_path / 'secrets.json').write_text('not read by Web')
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'production',
            'ENVIRONMENT': 'dev',
            'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT': 'https://mine.example.com',
            'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_DATABASE_NAME': 'mine',
            'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY': 'injected-by-deployment',
        },
    )
    assert reader.environment is WebEnvironment.PRODUCTION
    assert reader.external()['mina'].key == 'injected-by-deployment'


def test_production_rejects_incomplete_injected_connection(tmp_path) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'production',
            'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT': 'https://mine.example.com',
        },
    )
    with pytest.raises(ValueError, match='Incomplete'):
        reader.external()


def test_local_host_ignores_backend_environment_variable(tmp_path) -> None:
    (tmp_path / '.env').write_text(
        'ATLANTICUS_ENVIRONMENT=local\n'
        'ENVIRONMENT=dev\n'
        'ADA_APPLICATION_NAMESPACE=conciencia_situacional\n'
        'ADA_TOOL_NAMESPACE=command-center\n'
        'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true\n'
        'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME=configurations\n'
        'ADA_COMMAND_CENTER_COSMOS_ENDPOINT=https://command-center.example.com\n'
        'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME=command-center\n'
        'ADA_COMMAND_CENTER_COSMOS_KEY=secret-for-local-test\n'
    )
    reader = _local(tmp_path)
    own = reader.own()
    assert reader.environment is WebEnvironment.LOCAL
    assert own['ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME'] == 'configurations'
    assert 'ADA_COMMAND_CENTER_CATALOG_BLOB_NAME' not in own
    assert 'ADA_COMMAND_CENTER_ALARM_BLOB_CONTAINER' not in own


def test_manager_provider_accepts_local_or_durable_without_new_environment(tmp_path) -> None:
    (tmp_path / '.env').write_text('ADA_MANAGER_PERSISTENCE_PROVIDER=local\n')
    reader = _local(tmp_path, environ={'ADA_MANAGER_PERSISTENCE_PROVIDER': 'durable'})
    assert reader.manager_provider == 'durable'
    assert _local(tmp_path).manager_provider == 'local'
    default_reader = ManagerConfigurationReader(root=tmp_path, environ_supplier=lambda: {})
    assert default_reader.manager_provider == 'local'


def test_manager_provider_rejects_removed_example_modes(tmp_path) -> None:
    for mode in ('sample', 'durable-local', 'invalid'):
        reader = _local(tmp_path, environ={'ADA_MANAGER_PERSISTENCE_PROVIDER': mode})
        with pytest.raises(CommandCenterConfigurationError, match='provider'):
            _ = reader.manager_provider


def test_local_storage_does_not_require_own_cosmos(tmp_path) -> None:
    reader = _local(
        tmp_path,
        environ={
            'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional',
            'ADA_TOOL_NAMESPACE': 'command-center',
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations',
        },
    )
    assert len(reader.storage()) == 2
    with pytest.raises(CommandCenterConfigurationError, match='COSMOS_ENDPOINT'):
        reader.own()


def test_production_cannot_select_local_provider(tmp_path) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'production',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'local',
        },
    )
    with pytest.raises(CommandCenterConfigurationError, match='durable'):
        _ = reader.manager_provider
