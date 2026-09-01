from __future__ import annotations

from ada.processes.kpi_delivery.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'COSMOS_CONSUMPTION_ENDPOINT': 'http://localhost:8081',
        'COSMOS_CONSUMPTION_KEY': 'local-key',
        'COSMOS_CONSUMPTION_DATABASE_NAME': 'ada',
        'KPI_DELIVERY_CONFIGURATION_CONTAINER': 'config',
        'KPI_DELIVERY_CONFIGURATION_ITEM_ID': 'kpis',
        'KPI_DELIVERY_CONFIGURATION_PARTITION_KEY': 'kpis',
        'KPI_LATEST_DELIVERY_CONTAINER': 'latest',
        'KPI_DELIVERY_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_separates_own_runtime_from_kpi_runtime_authority(tmp_path) -> None:
    composition = build_composition(configuration=_configuration(tmp_path))

    assert composition.definition.module_name == 'ada.processes.kpi_delivery'
    assert composition.definition.service_name == 'kpi-delivery'
    assert composition.definition.job_key == 'kpi-delivery'
    assert composition.definition.sleep_seconds == 1
    assert composition.evaluations.paths.application_root == tmp_path / 'ada-kpi-runtime-local'
    assert composition.runtime_configuration.application == 'ada-kpi-delivery-local'
