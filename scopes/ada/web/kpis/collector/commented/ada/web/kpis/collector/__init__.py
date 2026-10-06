# API pública del Collector. Expone las dos identidades de Store y el decoder semántico de Latest
# para que los consumidores no reimplementen status/value_kind/value.

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
from ada.web.kpis.collector.latest import (
    DecodedKpiLatestValue,
    KpiLatestValueState,
    decode_kpi_latest_value,
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
    SystemKpiStoreSnapshot,
)
from ada.web.kpis.collector.presentation import (
    DEFAULT_KPI_BROWSER_REFRESH_INTERVAL_SECONDS,
    KPI_COMPONENT_STORE_TYPE,
    KPI_SYSTEM_STORE_TYPE,
    KpiCollectorPresentationSettings,
    component_kpi_store_id,
    project_component_store_data,
    project_system_store_data,
    resolve_kpi_collector_browser_update,
    system_kpi_destination_keys,
    system_kpi_store_id,
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
    'KPI_SYSTEM_STORE_TYPE',
    'AdaKpiCollector',
    'AdaKpiCollectorPollingRuntime',
    'AdaKpiCollectorWebIntegration',
    'DecodedKpiLatestValue',
    'KpiLatestValueState',
    'SystemKpiStoreSnapshot',
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
    'decode_kpi_latest_value',
    'project_component_store_data',
    'project_system_store_data',
    'resolve_kpi_collector_browser_update',
    'system_kpi_destination_keys',
    'system_kpi_store_id',
]
