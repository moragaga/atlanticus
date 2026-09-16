from collections.abc import Callable
from dataclasses import dataclass

from ada.web.kpis.configuration import KpiConfiguration
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class KpiDefinitionEditorContext:
    kpi_configuration_projection: ProjectionStore[KpiConfiguration]
    kpi_configuration_source_key: SourceKey
    can_manage: Callable[[], bool] = lambda: True
