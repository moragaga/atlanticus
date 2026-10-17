from __future__ import annotations

import json
from pathlib import Path

from ada.processes.kpi_historian.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path, *, reprocess_current: str = 'false') -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-historian-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'REPROCESS_CURRENT': reprocess_current,
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
    assert composition.definition.run_once is True
    assert composition.definition.poll_interval_seconds == 0
    assert composition.evaluations.paths.application_root == tmp_path / 'ada-kpi-runtime-local'
    assert composition.runtime_configuration.application == 'ada-kpi-historian-local'
    assert composition.settings.reprocess_current is False
    assert composition.rolling.path == (
        tmp_path / 'ada-kpi-historian-local' / 'timeseries' / 'current.parquet'
    )


def test_composition_propagates_reprocess_current(tmp_path) -> None:
    composition = build_composition(
        configuration=_configuration(tmp_path, reprocess_current='true')
    )

    assert composition.settings.reprocess_current is True


def test_historian_deployment_schedule_runs_once_per_minute() -> None:
    process_root = Path(__file__).resolve().parents[1]
    deployment = json.loads((process_root / 'config.detail.json').read_text(encoding='utf-8'))
    assert deployment['configuration']['triggerType'] == 'Schedule'
    assert deployment['configuration']['scheduleTriggerConfig']['cronExpression'] == '* * * * *'
    assert deployment['configuration']['scheduleTriggerConfig']['parallelism'] == 1
