from collections.abc import Callable
from dataclasses import dataclass

from ada.web.kpis.configuration import KpiDestinationCatalogProvider


@dataclass(frozen=True, slots=True)
class KpiConfigurationEditorContext:
    destinations: KpiDestinationCatalogProvider
    can_manage: Callable[[], bool] = lambda: True
