from ada.processes.kpi_delivery.composition import build_composition
from ada.processes.kpi_delivery.job import READINESS_RETRY_SECONDS
from ada.processes.kpi_delivery.models import KpiLatestDeliveryIterationStatus
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment
from tests.support import RuntimeContextStub


def _configuration(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-delivery-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'POLL_INTERVAL_SECONDS': '1',
        'KPI_DELIVERY_MAX_WORKERS': '2',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_starts_before_materialization_is_ready(tmp_path):
    connections = {
        'tool_a': CosmosSettings(
            endpoint='http://localhost:8081',
            database_name='ada-a',
            key='local-key',
            allow_insecure_http=True,
        )
    }

    composition = build_composition(
        configuration=_configuration(tmp_path),
        connections=connections,
    )
    try:
        context = RuntimeContextStub()
        result = composition.job.run_iteration(context)

        assert result.status is KpiLatestDeliveryIterationStatus.MATERIALIZATION_PENDING
        assert context.next_delay == READINESS_RETRY_SECONDS
        assert tuple(composition.publishers) == ('tool_a',)
        assert tuple(composition.clients) == ('tool_a',)
        assert composition.definition.sleep_seconds == 1
    finally:
        composition.parallel_publisher.close()
