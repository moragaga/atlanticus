from contextlib import contextmanager

import pytest

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.generic import runtime
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.users.local import LOCAL_USERS
from atlanticus.web.users.runtime import UsersRuntime


def test_local_launcher_rejects_production_before_opening_manager(tmp_path) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {'ATLANTICUS_ENVIRONMENT': 'production'},
    )

    with (
        pytest.raises(
            IdentityConfigurationError,
            match='injected production identity provider',
        ),
        runtime.open_local_application(reader=reader),
    ):
        pass


def test_local_launcher_selects_durable_manager_with_shared_users_runtime(
    tmp_path, monkeypatch
) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'durable',
            'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional',
            'ADA_TOOL_NAMESPACE': 'command-center',
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations',
            'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'http://cosmos-emulator:8081',
            'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command_center',
            'ADA_COMMAND_CENTER_COSMOS_KEY': 'test-only-key',
        },
    )
    observed = {}
    dependencies = object()
    application = object()

    @contextmanager
    def open_durable(*, reader, principal_provider):
        observed['reader'] = reader
        observed['principal_provider'] = principal_provider
        yield dependencies

    def create_application(
        current,
        *,
        identity_provider,
        users_runtime,
        master_material_reader,
        environment,
        namespace,
    ):
        observed['dependencies'] = current
        observed['identity'] = identity_provider
        observed['users_runtime'] = users_runtime
        observed['master_material_reader'] = master_material_reader
        observed['environment'] = environment
        observed['namespace'] = namespace
        return application

    monkeypatch.setattr(runtime, 'open_durable_configuration_manager', open_durable)
    monkeypatch.setattr(runtime, 'create_application', create_application)
    subject_id = LOCAL_USERS[0].subject_id

    with runtime.open_local_application(reader=reader, subject_id=subject_id) as resolved:
        assert resolved is application

    assert observed['reader'] is reader
    assert observed['dependencies'] is dependencies
    assert callable(observed['principal_provider'])
    assert observed['identity'].resolve(None).subject_id == subject_id
    assert isinstance(observed['users_runtime'], UsersRuntime)
    assert observed['environment'] is reader.environment
    assert observed['namespace'] == reader.namespace
    assert observed['master_material_reader'] is not None


def test_local_subject_defaults_to_atlanticus_local_user(monkeypatch) -> None:
    monkeypatch.delenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', raising=False)
    assert runtime._resolve_local_subject_id(None) == LOCAL_USERS[0].subject_id
