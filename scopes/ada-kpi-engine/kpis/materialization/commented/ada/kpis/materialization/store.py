# Espejo pedagógico del almacenamiento local atómico compartido por Materialization y Delivery.
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ada.kpis.materialization.contract import (
    require_tool_key,
    validate_materialized_registry,
)
from ada.kpis.materialization.errors import KpiMaterializationStoreError
from atlanticus.state import AtomicJsonStore, StateError


# Expone una operación del contrato manteniendo validación explícita.
def materialization_root(volume_path: str | Path) -> Path:
    if not isinstance(volume_path, str | Path):
        raise KpiMaterializationStoreError('VOLUMEN_PATH must be a filesystem path')
    if isinstance(volume_path, str) and volume_path != volume_path.strip():
        raise KpiMaterializationStoreError('VOLUMEN_PATH must not contain surrounding whitespace')
    path = Path(volume_path).expanduser()
    if not path.is_absolute():
        raise KpiMaterializationStoreError('VOLUMEN_PATH must be absolute')
    return path / 'ada-kpi-engine' / 'materialization' / 'registries'


# Agrupa una responsabilidad con estado o ciclo de vida propio.
class LocalKpiRegistryStore:
    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise KpiMaterializationStoreError('Materialization root must be an absolute Path')
        self._root = root
        self._store = AtomicJsonStore(root_path=root, max_document_bytes=None)

    @property
    def root(self) -> Path:
        return self._root

    def read(self, tool_key: str) -> dict[str, Any] | None:
        resolved_tool_key = require_tool_key(tool_key)
        self._validate_root()
        path = self._root / f'{resolved_tool_key}.json'
        if path.is_symlink():
            raise KpiMaterializationStoreError('Materialized KPI Registry cannot be a symlink')
        try:
            document = self._store.read(f'{resolved_tool_key}.json')
        except StateError as error:
            raise KpiMaterializationStoreError(
                f'Could not read materialized KPI Registry for {resolved_tool_key}'
            ) from error
        if document is None:
            return None
        return validate_materialized_registry(
            document,
            expected_tool_key=resolved_tool_key,
        )

    def replace(self, *, tool_key: str, document: Mapping[str, Any]) -> dict[str, Any]:
        resolved_tool_key = require_tool_key(tool_key)
        validated = validate_materialized_registry(
            document,
            expected_tool_key=resolved_tool_key,
        )
        self._validate_root()
        path = self._root / f'{resolved_tool_key}.json'
        if path.is_symlink():
            raise KpiMaterializationStoreError('Materialized KPI Registry cannot be a symlink')
        try:
            persisted = self._store.replace(f'{resolved_tool_key}.json', validated)
        except StateError as error:
            raise KpiMaterializationStoreError(
                f'Could not write materialized KPI Registry for {resolved_tool_key}'
            ) from error
        return validate_materialized_registry(
            persisted,
            expected_tool_key=resolved_tool_key,
        )

    def tool_keys(self) -> tuple[str, ...]:
        self._validate_root()
        if not self._root.exists():
            return ()
        keys: list[str] = []
        for path in sorted(self._root.glob('*.json')):
            if path.is_symlink() or not path.is_file():
                raise KpiMaterializationStoreError(
                    'Materialized KPI Registry path must be a regular file'
                )
            try:
                keys.append(require_tool_key(path.stem))
            except ValueError as error:
                raise KpiMaterializationStoreError(
                    f'Unexpected JSON file in KPI materialization root: {path.name}'
                ) from error
        return tuple(keys)

    def remove_unconfigured(self, active_tool_keys: Iterable[str]) -> tuple[str, ...]:
        active = frozenset(require_tool_key(value) for value in active_tool_keys)
        stale = tuple(key for key in self.tool_keys() if key not in active)
        if not stale:
            return ()
        try:
            for tool_key in stale:
                path = self._root / f'{tool_key}.json'
                if path.is_symlink() or not path.is_file():
                    raise KpiMaterializationStoreError(
                        'Materialized KPI Registry path must be a regular file'
                    )
                path.unlink()
            _fsync_directory(self._root)
        except KpiMaterializationStoreError:
            raise
        except OSError as error:
            raise KpiMaterializationStoreError(
                'Could not remove unconfigured materialized KPI Registries'
            ) from error
        return stale

    def _validate_root(self) -> None:
        if self._root.is_symlink():
            raise KpiMaterializationStoreError('Materialization root cannot be a symlink')
        if self._root.exists() and not self._root.is_dir():
            raise KpiMaterializationStoreError('Materialization root must be a directory')


# Expone una operación del contrato manteniendo validación explícita.
def _fsync_directory(path: Path) -> None:
    if os.name == 'nt' or not path.exists():
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
