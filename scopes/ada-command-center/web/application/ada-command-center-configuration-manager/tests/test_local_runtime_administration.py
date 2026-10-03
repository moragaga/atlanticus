from pathlib import Path

from ada_command_center.web.application.configuration_manager import (
    build_configuration_manager_surface,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    open_local_configuration_manager,
)
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.users.local import LOCAL_USERS


class StorageStub(StorageClient):
    def __init__(self, *, settings):
        self.settings = settings

    def download(self, *, container_name, blob_name):
        raise RuntimeError('unused')

    def upload(self, *, container_name, blob_name, data, **_kwargs):
        raise RuntimeError('unused')

    def close(self):
        pass


def test_local_runtime_mounts_administration_with_command_center_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    from ada_command_center.web.application.configuration_manager import local_runtime

    monkeypatch.setattr(local_runtime, 'StorageClient', StorageStub)
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'local',
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations',
        },
    )
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        profile_keys=('local',),
        access_keys=(),
        administrative_override=True,
        is_local=True,
    )

    with open_local_configuration_manager(
        reader=reader,
        principal_provider=lambda: principal,
        base_root=tmp_path,
    ) as dependencies:
        definition = build_configuration_manager_surface(dependencies)
        runtime_users = dependencies.administration.users_runtime_store.list_users()

    assert dependencies.administration is not None
    assert tuple(group.key for group in definition.groups) == ('administration', 'configuration')
    assert tuple(module.key for module in definition.modules) == (
        'profiles',
        'navigation',
        'alarm-configuration',
    )
    assert tuple(entry.key for entry in definition.entries) == ('users', 'tool-catalog')
    assert tuple(user.subject_id for user in runtime_users) == tuple(
        user.subject_id for user in LOCAL_USERS
    )
