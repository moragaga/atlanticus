# API pública del dominio KPI; expone tipos escalares y contratos sin incorporar dependencias de runtime.
from ada.kpis.core.catalog import KpiCatalog
from ada.kpis.core.enums import KpiArea, KpiMode, KpiStatus, KpiValueKind, KpiValueType
from ada.kpis.core.results import KpiEvaluation, KpiResult, KpiSourceTrace
from ada.kpis.core.rules import KpiResolver, KpiSpec, OverKpiResolver, OverKpiSpec
from ada.kpis.core.values import KpiJsonValue, KpiNativeValue, KpiScalar, normalize_kpi_value
from ada.kpis.core.watermark import KpiWatermark

__version__ = '1.0.0'

__all__ = [
    'KpiArea',
    'KpiCatalog',
    'KpiEvaluation',
    'KpiJsonValue',
    'KpiMode',
    'KpiNativeValue',
    'KpiResolver',
    'KpiResult',
    'KpiScalar',
    'KpiSourceTrace',
    'KpiSpec',
    'KpiStatus',
    'KpiValueKind',
    'KpiValueType',
    'KpiWatermark',
    'OverKpiResolver',
    'OverKpiSpec',
    '__version__',
    'normalize_kpi_value',
]
