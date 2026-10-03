from __future__ import annotations

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


class KpiDefinitionProjectionProvider:
    def __init__(
        self,
        *,
        projection_store: ProjectionStore[KpiDefinitionCatalog],
        source_key: SourceKey,
    ) -> None:
        self._projection_store = projection_store
        self._source_key = source_key

    def load_snapshot(self) -> KpiDefinitionSnapshot:
        projection = self._projection_store.get_active(self._source_key)
        if projection is None:
            return KpiDefinitionSnapshot(definitions=())
        return KpiDefinitionSnapshot(
            definitions=tuple(
                KpiDefinition(kpi_key=definition.kpi_key, fields=definition.fields)
                for definition in projection.payload.configuration.definitions
            )
        )
