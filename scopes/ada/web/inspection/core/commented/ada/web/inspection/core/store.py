from __future__ import annotations

from threading import Lock

from ada.web.inspection.core.contracts import KpiDefinition, KpiDefinitionSnapshot


# Mantiene un único snapshot local por proceso y no conoce providers, Cosmos ni lifecycle.
class KpiDefinitionSnapshotStore:
    def __init__(self, snapshot: KpiDefinitionSnapshot | None = None) -> None:
        # El lock protege el intercambio de referencia y los lookups frente a refresh concurrente.
        self._lock = Lock()
        # El índice privado permite resolver cada kpi_key en tiempo constante sin I/O remoto.
        self._definitions: dict[str, KpiDefinition] = {}
        if snapshot is not None:
            self.replace(snapshot)

    def get(self, kpi_key: str) -> KpiDefinition | None:
        # La ausencia de definición es válida, pero una identidad vacía es un error de contrato.
        if not isinstance(kpi_key, str) or not kpi_key.strip():
            raise ValueError('KPI key must be a non-empty string')
        with self._lock:
            return self._definitions.get(kpi_key)

    def replace(self, snapshot: KpiDefinitionSnapshot) -> None:
        if not isinstance(snapshot, KpiDefinitionSnapshot):
            raise TypeError('Snapshot must be a KpiDefinitionSnapshot')

        # El nuevo índice se construye completamente fuera del lock. Si esta construcción falla,
        # el store conserva intacto el snapshot anterior.
        definitions = {definition.kpi_key: definition for definition in snapshot.definitions}

        # Sólo el cambio de referencia ocurre bajo lock; nunca se muta el diccionario publicado.
        with self._lock:
            self._definitions = definitions
