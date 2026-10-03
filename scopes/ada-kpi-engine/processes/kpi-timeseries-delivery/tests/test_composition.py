from ada.processes.kpi_timeseries_delivery.composition import build_composition
from ada.processes.kpi_timeseries_delivery.job import READINESS_RETRY_SECONDS
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesDeliveryIterationStatus,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment
from tests.support import RuntimeContextStub


def _configuration(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-timeseries-delivery-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'KPI_HISTORIAN_APPLICATION': 'ada-kpi-historian-local',
        'KPI_TIMESERIES_DELIVERY_POLL_INTERVAL_SECONDS': '1',
        'KPI_TIMESERIES_DELIVERY_MAX_WORKERS': '2',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_starts_with_multiple_tools_before_materialization_is_ready(tmp_path):
    connections = {
        'tool_a': CosmosSettings(
            endpoint='http://localhost:8081',
            database_name='ada-a',
            key='local-key-a',
            allow_insecure_http=True,
        ),
        'tool_b': CosmosSettings(
            endpoint='http://localhost:8081',
            database_name='ada-b',
            key='local-key-b',
            allow_insecure_http=True,
        ),
    }
    composition = build_composition(
        configuration=_configuration(tmp_path),
        connections=connections,
    )
    try:
        context = RuntimeContextStub()
        result = composition.job.run_iteration(context)

        assert result.status is KpiTimeseriesDeliveryIterationStatus.MATERIALIZATION_PENDING
        assert result.tool_count == 2
        assert context.next_delay == READINESS_RETRY_SECONDS
        assert tuple(composition.publishers) == ('tool_a', 'tool_b')
        assert tuple(composition.clients) == ('tool_a', 'tool_b')
        assert composition.definition.sleep_seconds == 1
        assert composition.settings.max_workers == 2
    finally:
        composition.parallel_publisher.close()
        for client in composition.clients.values():
            client.close()
