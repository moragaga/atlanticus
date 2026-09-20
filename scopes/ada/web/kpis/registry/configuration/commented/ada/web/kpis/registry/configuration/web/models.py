from collections.abc import Callable
from dataclasses import dataclass

from ada.web.kpis.registry.configuration import KpiDestinationCatalogProvider


@dataclass(frozen=True, slots=True)
class KpiRegistryEditorContext:
    destinations: KpiDestinationCatalogProvider
    can_manage: Callable[[], bool] = lambda: True
