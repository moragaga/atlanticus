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
