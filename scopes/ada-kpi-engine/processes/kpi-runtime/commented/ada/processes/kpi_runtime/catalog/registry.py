# El registro es la única autoridad de composición; agregar una carpeta no activa KPI automáticamente.
from ada.kpis.core import KpiCatalog
from ada.processes.kpi_runtime.catalog.general.over.specs import (
    OVER_SPECS as GENERAL_OVER_SPECS,
)
from ada.processes.kpi_runtime.catalog.general.specs import SPECS as GENERAL_SPECS


def build_catalog() -> KpiCatalog:
    return KpiCatalog(
        specs=GENERAL_SPECS,
        over_specs=GENERAL_OVER_SPECS,
    )
