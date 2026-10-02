from contextlib import contextmanager

import pytest

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.generic import runtime
from atlanticus.web.identity.errors import IdentityConfigurationError


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


def test_local_launcher_selects_durable_manager_without_changing_identity_mode(
    tmp_path, monkeypatch
) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'durable',
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
        observed['principal'] = principal_provider()
        yield dependencies

    def create_application(current, *, identity_provider):
        observed['dependencies'] = current
        observed['identity'] = identity_provider
        return application

    monkeypatch.setattr(runtime, 'open_durable_configuration_manager', open_durable)
    monkeypatch.setattr(runtime, 'create_application', create_application)

    with runtime.open_local_application(reader=reader, subject_id='local:test') as resolved:
        assert resolved is application

    assert observed['reader'] is reader
    assert observed['dependencies'] is dependencies
    assert observed['principal'].subject_id == 'local:test'
    assert observed['principal'].administrative_override is True
    assert observed['principal'].is_local is True
    assert observed['identity'].resolve(None).subject_id == 'local:test'
