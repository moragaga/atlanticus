from __future__ import annotations

from threading import Lock

from ada.web.inspection.core.contracts import KpiDefinition, KpiDefinitionSnapshot


class KpiDefinitionSnapshotStore:
    def __init__(self, snapshot: KpiDefinitionSnapshot | None = None) -> None:
        self._lock = Lock()
        self._definitions: dict[str, KpiDefinition] = {}
        if snapshot is not None:
            self.replace(snapshot)

    def get(self, kpi_key: str) -> KpiDefinition | None:
        if not isinstance(kpi_key, str) or not kpi_key.strip():
            raise ValueError('KPI key must be a non-empty string')
        with self._lock:
            return self._definitions.get(kpi_key)

    def replace(self, snapshot: KpiDefinitionSnapshot) -> None:
        if not isinstance(snapshot, KpiDefinitionSnapshot):
            raise TypeError('Snapshot must be a KpiDefinitionSnapshot')
        definitions = {definition.kpi_key: definition for definition in snapshot.definitions}
        with self._lock:
            self._definitions = definitions
