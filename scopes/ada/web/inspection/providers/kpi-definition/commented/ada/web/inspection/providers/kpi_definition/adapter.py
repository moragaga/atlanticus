from __future__ import annotations

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


# Este adapter es la única frontera entre la proyección descriptiva y el contrato reusable
# de Inspection. No conoce Cosmos ni el lifecycle de warmup/refresh.
class KpiDefinitionProjectionProvider:
    def __init__(
        self,
        *,
        projection_store: ProjectionStore[KpiDefinitionCatalog],
        source_key: SourceKey,
    ) -> None:
        # El store genérico y la identidad de Source se inyectan para mantener fuera
        # del adapter la topología física y la composición específica de KPI Definition.
        self._projection_store = projection_store
        self._source_key = source_key

    def load_snapshot(self) -> KpiDefinitionSnapshot:
        # Cada carga corresponde a una decisión explícita del lifecycle, nunca a un click.
        projection = self._projection_store.get_active(self._source_key)
        if projection is None:
            # La ausencia de proyección equivale a un catálogo descriptivo vacío y válido.
            return KpiDefinitionSnapshot(definitions=())
        # El ProjectionRecord vigente contiene KpiDefinitionCatalog como payload; Inspection
        # traduce únicamente la configuración autoritativa del catálogo a su snapshot propio.
        return KpiDefinitionSnapshot(
            definitions=tuple(
                KpiDefinition(kpi_key=definition.kpi_key, fields=definition.fields)
                for definition in projection.payload.configuration.definitions
            )
        )
