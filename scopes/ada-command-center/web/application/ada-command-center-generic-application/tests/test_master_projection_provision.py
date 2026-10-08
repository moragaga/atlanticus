from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.generic.master_projection import provision


def test_local_master_projection_provision_uses_derived_location(tmp_path: Path) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'local',
            'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional',
            'ADA_TOOL_NAMESPACE': 'command-center',
        },
    )
    runtime_root = tmp_path / 'runtime'

    result = provision._generate_local(
        reader,
        service_user='service-user',
        password='0123456789abcdef',
        base_root=runtime_root,
    )

    target = (
        runtime_root
        / 'conciencia_situacional'
        / 'command-center'
        / 'master-projection'
        / 'material.zip'
    )
    assert target.is_file()
    assert result['persistence'] == 'local'
    assert result['location'] == str(target)
