from __future__ import annotations

from ada.processes.kpi_historian.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-historian-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'KPI_HISTORIAN_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_separates_historian_from_kpi_runtime_authority(tmp_path) -> None:
    composition = build_composition(configuration=_configuration(tmp_path))

    assert composition.definition.module_name == 'ada.processes.kpi_historian'
    assert composition.definition.service_name == 'kpi-historian'
    assert composition.definition.job_key == 'kpi-historian'
    assert composition.definition.sleep_seconds == 1
    assert composition.evaluations.paths.application_root == tmp_path / 'ada-kpi-runtime-local'
    assert composition.runtime_configuration.application == 'ada-kpi-historian-local'
