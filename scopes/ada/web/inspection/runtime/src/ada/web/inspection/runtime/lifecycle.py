from __future__ import annotations

from ada.web.inspection.core import (
    KpiDefinitionProvider,
    KpiDefinitionSnapshot,
    KpiDefinitionSnapshotStore,
)


class KpiDefinitionWarmup:
    def __init__(
        self,
        provider: KpiDefinitionProvider,
        store: KpiDefinitionSnapshotStore,
    ) -> None:
        self._provider = provider
        self._store = store

    def run(self) -> KpiDefinitionSnapshot:
        snapshot = self._provider.load_snapshot()
        self._store.replace(snapshot)
        return snapshot


class KpiDefinitionRefresh:
    def __init__(
        self,
        provider: KpiDefinitionProvider,
        store: KpiDefinitionSnapshotStore,
    ) -> None:
        self._provider = provider
        self._store = store

    def run(self) -> KpiDefinitionSnapshot:
        snapshot = self._provider.load_snapshot()
        self._store.replace(snapshot)
        return snapshot
