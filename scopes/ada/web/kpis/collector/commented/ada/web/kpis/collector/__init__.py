# API pública del collector KPI. Los consumidores importan desde este módulo sin depender de
# archivos internos ni de detalles de composición.

from ada.web.kpis.collector.collector import AdaKpiCollector
from ada.web.kpis.collector.cosmos import (
    DEFAULT_KPI_LATEST_DELIVERY_CONTAINER,
    DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER,
    CosmosKpiDeliveryReader,
    CosmosKpiDeliveryReaderSettings,
)
from ada.web.kpis.collector.integration import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    ADA_KPI_COLLECTOR_SERVICE_KEY,
    AdaKpiCollectorWebIntegration,
    attach_ada_kpi_collector,
    create_ada_kpi_collector_module,
    create_ada_kpi_collector_web_integration,
)
from ada.web.kpis.collector.models import (
    ComponentKpiData,
    ComponentLatestKpiData,
    ComponentTimeseriesKpiData,
    KpiCollectorContractError,
    KpiCollectorError,
    KpiCollectorRefreshResult,
    KpiCollectorRefreshStatus,
    KpiCollectorSnapshot,
    KpiDeliveryReader,
    KpiDeliveryReadError,
)
from ada.web.kpis.collector.presentation import (
    DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS,
    KPI_COMPONENT_STORE_TYPE,
    KpiCollectorPresentationSettings,
    component_kpi_store_id,
    project_component_store_data,
    resolve_kpi_collector_browser_update,
)
from ada.web.kpis.collector.runtime import (
    DEFAULT_KPI_LATEST_INTERVAL_SECONDS,
    DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS,
    AdaKpiCollectorPollingRuntime,
    KpiCollectorPollCycle,
    KpiCollectorPollingSettings,
)

__all__ = [
    'ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY',
    'ADA_KPI_COLLECTOR_SERVICE_KEY',
    'DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS',
    'DEFAULT_KPI_LATEST_DELIVERY_CONTAINER',
    'DEFAULT_KPI_LATEST_INTERVAL_SECONDS',
    'DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER',
    'DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS',
    'KPI_COMPONENT_STORE_TYPE',
    'AdaKpiCollector',
    'AdaKpiCollectorPollingRuntime',
    'AdaKpiCollectorWebIntegration',
    'attach_ada_kpi_collector',
    'ComponentKpiData',
    'ComponentLatestKpiData',
    'ComponentTimeseriesKpiData',
    'CosmosKpiDeliveryReader',
    'CosmosKpiDeliveryReaderSettings',
    'KpiCollectorContractError',
    'KpiCollectorError',
    'KpiCollectorPollCycle',
    'KpiCollectorPollingSettings',
    'KpiCollectorPresentationSettings',
    'KpiCollectorRefreshResult',
    'KpiCollectorRefreshStatus',
    'KpiCollectorSnapshot',
    'KpiDeliveryReadError',
    'KpiDeliveryReader',
    'component_kpi_store_id',
    'create_ada_kpi_collector_module',
    'create_ada_kpi_collector_web_integration',
    'project_component_store_data',
    'resolve_kpi_collector_browser_update',
]
