from pathlib import Path

from ada_command_center.web.application.generic.master_projection.location import (
    COMMAND_CENTER_MASTER_APPLICATION_NAMESPACE,
    COMMAND_CENTER_MASTER_BLOB_NAME,
    MASTER_PROJECTION_RELATIVE_PATH,
    master_projection_local_path,
)


def test_master_projection_identity_is_isolated_inside_command_center_namespace(
    tmp_path: Path,
) -> None:
    assert COMMAND_CENTER_MASTER_APPLICATION_NAMESPACE == 'conciencia_situacional/command-center'
    assert COMMAND_CENTER_MASTER_BLOB_NAME == (
        'conciencia_situacional/command-center/master-projection/material.zip'
    )
    assert master_projection_local_path(tmp_path) == (
        tmp_path / 'conciencia_situacional' / 'command-center' / MASTER_PROJECTION_RELATIVE_PATH
    )
