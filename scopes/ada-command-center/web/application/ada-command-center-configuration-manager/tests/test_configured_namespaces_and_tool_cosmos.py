from __future__ import annotations

import pytest

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    CommandCenterConfigurationError,
    ManagerConfigurationReader,
    resolve_command_center_namespace,
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    resolve_durable_configuration,
)
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
)
from atlanticus.web.storage.namespace import StorageNamespace


def _own() -> dict[str, str]:
    return {
        'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional',
        'ADA_TOOL_NAMESPACE': 'command-center',
        'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'dataproduct',
        'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'https://command-center.example.test',
        'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command_center',
        'ADA_COMMAND_CENTER_COSMOS_KEY': 'unit-test-key',
    }


def _external(database: str = 'tool_mina') -> dict[str, str]:
    return {
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT': 'https://command-center.example.test',
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_DATABASE_NAME': database,
        'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY': 'unit-test-key',
    }


def _reader(tmp_path, values):
    return ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {'ATLANTICUS_ENVIRONMENT': 'local', **values},
    )


def test_namespaces_must_be_explicit_and_match_atlanticus_generic_contract():
    with pytest.raises(CommandCenterConfigurationError, match='ADA_APPLICATION_NAMESPACE'):
        resolve_command_center_namespace({})
    with pytest.raises(CommandCenterConfigurationError, match='ADA_TOOL_NAMESPACE'):
        resolve_command_center_namespace({'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional'})
    namespace = resolve_command_center_namespace(_own())
    assert namespace == StorageNamespace('conciencia_situacional', 'command-center')
    assert namespace.scope_prefix == 'conciencia_situacional/command-center'
    assert namespace.application_blob_name('users/users.json.gz') == (
        'conciencia_situacional/users/users.json.gz'
    )


def test_namespace_is_configurable_for_all_command_center_durable_paths():
    values = {
        **_own(),
        'ADA_APPLICATION_NAMESPACE': 'another_application',
        'ADA_TOOL_NAMESPACE': 'administrator',
    }
    result = resolve_durable_configuration(values, local=True)
    assert result.namespace.scope_prefix == 'another_application/administrator'
    assert result.source_root_prefix == 'another_application/administrator'
    assert result.catalog_blob_name == 'another_application/administrator/tool-catalog/current.json'
    assert result.users_registry_blob_name == 'another_application/users/users.json.gz'
    assert result.users_membership_blob_name == (
        'another_application/administrator/users/memberships.json.gz'
    )
    assert result.alarm_projection_container_name == 'alarm-configuration'
    assert result.cosmos_settings.database_name == 'command_center'


def test_reader_uses_env_file_then_process_override(tmp_path):
    (tmp_path / '.env').write_text(
        'ATLANTICUS_ENVIRONMENT=local\n'
        'ADA_APPLICATION_NAMESPACE=from_file\n'
        'ADA_TOOL_NAMESPACE=scope_file\n'
    )
    from_file = ManagerConfigurationReader(root=tmp_path, environ_supplier=lambda: {})
    assert from_file.namespace.scope_prefix == 'from_file/scope_file'
    from_process = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {'ADA_TOOL_NAMESPACE': 'scope_process'},
    )
    assert from_process.namespace.scope_prefix == 'from_file/scope_process'


@pytest.mark.parametrize(
    'variable,value',
    [('ADA_APPLICATION_NAMESPACE', 'a/b'), ('ADA_TOOL_NAMESPACE', ''), ('ADA_TOOL_NAMESPACE', '..')],
)
def test_namespace_rejects_invalid_path_segments(tmp_path, variable, value):
    reader = _reader(tmp_path, {**_own(), variable: value})
    with pytest.raises(CommandCenterConfigurationError, match='namespace'):
        _ = reader.namespace


def test_own_configuration_includes_effective_namespace(tmp_path):
    reader = _reader(
        tmp_path,
        {**_own(), 'ADA_APPLICATION_NAMESPACE': 'configured', 'ADA_TOOL_NAMESPACE': 'cc'},
    )
    assert resolve_durable_configuration(reader.own(), local=True).namespace.scope_prefix == (
        'configured/cc'
    )


def test_external_tool_must_not_reuse_own_cosmos_database(tmp_path):
    reader = _reader(
        tmp_path,
        {
            **_own(),
            **_external('command_center'),
            'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT': 'https://COMMAND-CENTER.example.test/',
        },
    )
    with pytest.raises(CommandCenterConfigurationError, match='must not target'):
        reader.external()


def test_external_tool_can_share_cosmos_endpoint_with_different_database(tmp_path):
    reader = _reader(tmp_path, {**_own(), **_external()})
    assert reader.external()['mina'].database_name == 'tool_mina'


def test_external_tool_can_have_a_separate_cosmos_endpoint(tmp_path):
    reader = _reader(
        tmp_path,
        {
            **_own(),
            **_external('command_center'),
            'ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT': 'https://other.example.test',
        },
    )
    assert reader.external()['mina'].database_name == 'command_center'


def test_storage_credential_modes_use_atlanticus_settings():
    connection = catalog_storage_settings(_own())
    assert isinstance(connection.credential, StorageConnectionStringCredential)
    values = _own()
    del values['ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING']
    values['ADA_COMMAND_CENTER_STORAGE_ACCOUNT_URL'] = 'http://localhost:10000/devstoreaccount1'
    values['ADA_COMMAND_CENTER_STORAGE_SAS_TOKEN'] = 'sig=test'
    settings = catalog_storage_settings(values, allow_insecure_http=True)
    assert isinstance(settings.credential, StorageSasCredential)
    assert settings.credential.allow_insecure_http is True


@pytest.mark.parametrize('missing', ['ADA_COMMAND_CENTER_STORAGE_ACCOUNT_URL', 'ADA_COMMAND_CENTER_STORAGE_SAS_TOKEN'])
def test_incomplete_sas_fails_without_fallback(missing):
    values = _own()
    del values['ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING']
    values.update({
        'ADA_COMMAND_CENTER_STORAGE_ACCOUNT_URL': 'https://account.example.test',
        'ADA_COMMAND_CENTER_STORAGE_SAS_TOKEN': 'sig=test',
    })
    del values[missing]
    with pytest.raises(CommandCenterConfigurationError, match='Storage requires'):
        catalog_storage_settings(values)


def test_mixed_storage_credentials_are_rejected(tmp_path):
    values = _own()
    values['ADA_COMMAND_CENTER_STORAGE_ACCOUNT_URL'] = 'https://account.example.test'
    values['ADA_COMMAND_CENTER_STORAGE_SAS_TOKEN'] = 'sig=test'
    with pytest.raises(CommandCenterConfigurationError, match='mutually exclusive'):
        catalog_storage_settings(values)
    with pytest.raises(CommandCenterConfigurationError, match='mutually exclusive'):
        _reader(tmp_path, values).own()


def test_durable_external_requires_admin_identity_and_is_independent_of_storage(tmp_path):
    values = {**_own(), **_external()}
    values['ADA_MANAGER_PERSISTENCE_PROVIDER'] = 'durable'
    del values['ADA_COMMAND_CENTER_COSMOS_ENDPOINT']
    with pytest.raises(CommandCenterConfigurationError, match='COSMOS_ENDPOINT'):
        _reader(tmp_path, values).external()


def test_durable_excludes_own_database_even_with_explicit_other_tool_name(tmp_path):
    values = {**_own(), **_external('command_center')}
    values['ADA_MANAGER_PERSISTENCE_PROVIDER'] = 'durable'
    with pytest.raises(CommandCenterConfigurationError, match='must not target'):
        _reader(tmp_path, values).external()
