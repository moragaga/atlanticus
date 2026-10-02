from __future__ import annotations

# Espejo pedagógico: la identidad física de Master Projection se deriva del namespace de Command Center.
from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    COMMAND_CENTER_NAMESPACE,
)

MASTER_PROJECTION_RELATIVE_PATH = 'master-projection/material.zip'
COMMAND_CENTER_MASTER_APPLICATION_NAMESPACE = COMMAND_CENTER_NAMESPACE.scope_prefix
COMMAND_CENTER_MASTER_BLOB_NAME = COMMAND_CENTER_NAMESPACE.scope_blob_name(
    MASTER_PROJECTION_RELATIVE_PATH
)


def master_projection_local_path(base_root: Path) -> Path:
    root = Path(base_root).expanduser()
    if not root.is_absolute():
        raise ValueError('Command Center Master Projection base root must be absolute')
    return COMMAND_CENTER_NAMESPACE.local_scope_root(root) / MASTER_PROJECTION_RELATIVE_PATH
