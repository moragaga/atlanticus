# Espejo pedagógico del contrato productivo.
# La implementación conserva las mismas clases y funciones; estos comentarios explican la intención general.
# Definition consume directamente la proyección tipada de KPI Configuration y delega identidad/versionado a Atlanticus.
from collections.abc import Callable
from dataclasses import dataclass

from ada.web.kpis.registry.models import KpiRegistry
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class KpiDefinitionEditorContext:
    kpi_registry_projection: ProjectionStore[KpiRegistry]
    kpi_registry_source_key: SourceKey
    can_manage: Callable[[], bool] = lambda: True
