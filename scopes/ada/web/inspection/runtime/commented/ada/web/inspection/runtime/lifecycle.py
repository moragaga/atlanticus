from __future__ import annotations

from ada.web.inspection.core import (
    KpiDefinitionProvider,
    KpiDefinitionSnapshot,
    KpiDefinitionSnapshotStore,
)


# Mantiene las dependencias del warmup inyectadas para que el runtime no conozca Cosmos ni una composición concreta.
class KpiDefinitionWarmup:
    # Recibe el proveedor de definiciones y el store que pertenece al proceso/worker que hospeda la capability.
    def __init__(
        self,
        provider: KpiDefinitionProvider,
        store: KpiDefinitionSnapshotStore,
    ) -> None:
        self._provider = provider
        self._store = store

    # Carga primero un snapshot completo y sólo después lo publica mediante el reemplazo atómico del store.
    def run(self) -> KpiDefinitionSnapshot:
        snapshot = self._provider.load_snapshot()
        self._store.replace(snapshot)
        return snapshot
