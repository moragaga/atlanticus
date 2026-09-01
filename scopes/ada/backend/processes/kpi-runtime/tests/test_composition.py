from __future__ import annotations

from ada.kpis.core import KpiCatalog
from ada.processes.kpi_runtime.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-runtime-local',
        'VOLUMEN_PATH': str(tmp_path),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'operational-data-notpii-local',
        'KPI_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_uses_job_runtime_and_empty_catalog(tmp_path) -> None:
    composition = build_composition(
        configuration=_configuration(tmp_path),
        catalog=KpiCatalog(()),
    )

    assert composition.definition.module_name == 'ada.processes.kpi_runtime'
    assert composition.definition.service_name == 'kpi-runtime'
    assert composition.definition.job_key == 'kpi-runtime'
    assert composition.definition.sleep_seconds == 1
    assert composition.definition.iteration_timeout_seconds == 240
    assert composition.definition.execution_timeout_seconds == 600
    assert len(composition.catalog) == 0
