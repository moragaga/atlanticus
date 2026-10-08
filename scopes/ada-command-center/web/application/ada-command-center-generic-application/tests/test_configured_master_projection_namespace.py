from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.generic.master_projection import provision
from ada_command_center.web.application.generic.master_projection.location import (
    master_projection_blob_name,
    master_projection_local_path,
)


def _reader(tmp_path):
    return ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'local',
            'ADA_APPLICATION_NAMESPACE': 'custom_ada',
            'ADA_TOOL_NAMESPACE': 'command_admin',
        },
    )


def test_master_projection_uses_reader_namespace_in_both_backends(tmp_path: Path):
    reader = _reader(tmp_path)
    root = tmp_path / 'persisted'
    expected = root / 'custom_ada' / 'command_admin' / 'master-projection' / 'material.zip'
    assert master_projection_local_path(root, namespace=reader.namespace) == expected
    assert master_projection_blob_name(reader.namespace) == (
        'custom_ada/command_admin/master-projection/material.zip'
    )


def test_local_master_material_generated_at_configured_location(tmp_path: Path):
    reader = _reader(tmp_path)
    result = provision._generate_local(
        reader,
        service_user='service-user',
        password='0123456789abcdef',
        base_root=tmp_path / 'material',
    )
    expected = (
        tmp_path
        / 'material'
        / 'custom_ada'
        / 'command_admin'
        / 'master-projection'
        / 'material.zip'
    )
    assert result['location'] == str(expected)
    assert expected.is_file()
