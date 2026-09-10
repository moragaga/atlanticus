# Espejo comentado de la superficie Web de KPI Definition.
from collections.abc import Callable
from dataclasses import dataclass

from ada.web.kpis.definition import KpiDefinitionAuthorityProvider


@dataclass(frozen=True, slots=True)
class KpiDefinitionEditorContext:
    authority: KpiDefinitionAuthorityProvider
    can_manage: Callable[[], bool] = lambda: True
