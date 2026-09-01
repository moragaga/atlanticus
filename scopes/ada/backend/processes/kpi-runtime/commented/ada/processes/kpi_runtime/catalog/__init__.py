# Espejo pedagógico: el catálogo productivo se mantiene vacío hasta incorporar definiciones KPI explícitas.
from ada.kpis.core import KpiCatalog


def build_catalog() -> KpiCatalog:
    return KpiCatalog(())
