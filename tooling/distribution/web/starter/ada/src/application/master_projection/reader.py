from __future__ import annotations

import hashlib
from pathlib import Path

from application.master_projection.material import (
    MasterMaterialIdentity,
    inspect_master_material,
    unlock_master_material,
)

_ARCHIVE_LIMIT = 24576


class StarterMasterMaterialReader:
    def __init__(self, path: Path | None) -> None:
        if path is not None and not path.is_absolute():
            raise ValueError('Master Projection material path must be absolute')
        self._path = path

    def inspect(self) -> str:
        return 'ABSENT' if self._path is None else str(inspect_master_material(self._path))

    def fingerprint(self) -> str | None:
        if self._path is None or self.inspect() != 'PRESENT':
            return None
        try:
            with self._path.open('rb') as source:
                content = source.read(_ARCHIVE_LIMIT + 1)
            if not content or len(content) > _ARCHIVE_LIMIT:
                return None
            return hashlib.sha256(content).hexdigest()
        except OSError:
            return None

    def unlock(
        self, *, service_user: str, password: str,
        application_namespace: str, environment: str,
    ) -> MasterMaterialIdentity:
        if self._path is None:
            raise RuntimeError('Master Projection material is not configured')
        return unlock_master_material(
            self._path,
            service_user=service_user,
            password=password,
            application_namespace=application_namespace,
            environment=environment,
        )
