from __future__ import annotations

from pathlib import Path

import pytest

import ada_command_center.processes.alarms_runtime.process as process_module
import ada_command_center.processes.alarms_runtime.source_reader as source_reader
from ada_command_center.processes.alarms_runtime.application import build_application
from ada_command_center.processes.alarms_runtime.source_adapter import AlarmDataSourceAdapter
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment
from atlanticus.operational_data.sources import DataSourceApplications, PiSourceProvider
from atlanticus.runtime import RuntimeConfiguration


def test_application_wires_existing_job_and_preserves_execution_environment(
    tmp_path: Path, monkeypatch
):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-command-center',
        'VOLUMEN_PATH': str(tmp_path),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'notpii-local',
        'ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY': 'test.technical',
        'ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION': 'v1',
        'ALARM_RUNTIME_POLL_SECONDS': '5',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    process = build_application(configuration=configuration)
    assert process.configuration == RuntimeConfiguration.from_sources(environ=configuration.values)
    assert process.definition.sleep_seconds == 5
    assert process.job.iteration_executor.evaluator_registry.contracts == ()
    assert isinstance(process.operational_runner.source_loader, AlarmDataSourceAdapter)
    calls = []

    def execute_job(**kwargs):
        calls.append(kwargs)
        return 'executed'

    monkeypatch.setattr(process_module, 'execute_alarm_runtime_job', execute_job)
    assert process.execute(argv=('--run-once',), environ=configuration.values) == 'executed'
    assert calls[0]['definition'] is process.definition
    assert calls[0]['environ'] is configuration.values
    assert calls[0]['argv'] == ('--run-once',)

    with pytest.raises(ValueError, match='execution environment'):
        process.execute(environ={**configuration.values, 'APPLICATION': 'another-process'})


def test_source_routing_materializes_physical_contract_only_at_reader_boundary(
    tmp_path: Path, monkeypatch
):
    captured = {}
    expected = object()

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(source_reader, 'build_alarm_source_adapter', fake_builder)
    result = source_reader.build_configured_alarm_source_adapter(
        volume_path=tmp_path,
        pi_source='pi_web_api',
        pi_application='pi-local',
        dispatch_application='dispatch-local',
        blockgrade_application=None,
        remanentes_application=None,
        fabrica_planes_application=None,
    )
    assert result is expected
    assert captured['volume_path'] == tmp_path
    assert captured['pi_source'] is PiSourceProvider.PI_WEB_API
    assert captured['applications'] == DataSourceApplications(
        pi='pi-local', dispatch='dispatch-local'
    )
