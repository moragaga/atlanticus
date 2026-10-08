from pathlib import Path

from ada_command_center.web.application.generic.master_projection.location import (
    master_projection_blob_name,
    MASTER_PROJECTION_RELATIVE_PATH,
    master_projection_local_path,
)
from atlanticus.web.storage.namespace import StorageNamespace


def test_master_projection_identity_is_isolated_inside_command_center_namespace(
    tmp_path: Path,
) -> None:
    namespace = StorageNamespace('conciencia_situacional', 'command-center')
    assert master_projection_blob_name(namespace) == (
        'conciencia_situacional/command-center/master-projection/material.zip'
    )
    assert master_projection_local_path(tmp_path, namespace=namespace) == (
        tmp_path / 'conciencia_situacional' / 'command-center' / MASTER_PROJECTION_RELATIVE_PATH
    )
