# API pública del dominio KPI Delivery.
# Este módulo sólo reexporta contratos y funciones puras; no compone runtime ni infraestructura.

from ada.kpis.delivery.configuration import KpiDeliveryBinding, KpiDeliveryConfiguration
from ada.kpis.delivery.errors import KpiDeliveryValidationError
from ada.kpis.delivery.latest import project_kpi_latest
from ada.kpis.delivery.models import (
    KpiDeliveryStatus,
    KpiLatestManifest,
    KpiLatestSnapshot,
    KpiLatestValue,
    KpiTimeseriesManifest,
    KpiTimeseriesSeries,
    KpiTimeseriesSnapshot,
)
from ada.kpis.delivery.revision import canonical_revision
from ada.kpis.delivery.timeseries import (
    TIMESERIES_STEP_SECONDS,
    align_timeseries_end,
    project_kpi_timeseries,
)

__all__ = [
    'TIMESERIES_STEP_SECONDS',
    'KpiDeliveryBinding',
    'KpiDeliveryConfiguration',
    'KpiDeliveryStatus',
    'KpiDeliveryValidationError',
    'KpiLatestManifest',
    'KpiLatestSnapshot',
    'KpiLatestValue',
    'KpiTimeseriesManifest',
    'KpiTimeseriesSeries',
    'KpiTimeseriesSnapshot',
    'align_timeseries_end',
    'canonical_revision',
    'project_kpi_latest',
    'project_kpi_timeseries',
]
