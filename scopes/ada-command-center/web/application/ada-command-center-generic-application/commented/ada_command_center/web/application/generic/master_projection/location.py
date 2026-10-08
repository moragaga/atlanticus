from __future__ import annotations

# Espejo pedagógico: la identidad física de Master Projection se deriva del namespace de Command Center.
from pathlib import Path

from atlanticus.web.storage.namespace import StorageNamespace

MASTER_PROJECTION_RELATIVE_PATH = 'master-projection/material.zip'


# Lector y generador resuelven la misma ubicación.
def master_projection_blob_name(namespace: StorageNamespace) -> str:
    return namespace.scope_blob_name(MASTER_PROJECTION_RELATIVE_PATH)


def master_projection_local_path(base_root: Path, *, namespace: StorageNamespace) -> Path:
    root = Path(base_root).expanduser()
    if not root.is_absolute():
        raise ValueError('Command Center Master Projection base root must be absolute')
    return namespace.local_scope_root(root) / MASTER_PROJECTION_RELATIVE_PATH
