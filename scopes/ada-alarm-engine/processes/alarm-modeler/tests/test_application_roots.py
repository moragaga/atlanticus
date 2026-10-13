from __future__ import annotations

from pathlib import Path

from ada.processes.alarm_modeler.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(
    *, volume_path: Path, application: str, runtime_application: str
) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': application,
        'VOLUMEN_PATH': str(volume_path),
        'ALARM_RUNTIME_APPLICATION': runtime_application,
        'ALARM_MODELER_POLL_SECONDS': '1',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_shared_application_keeps_runtime_and_modeler_current_paths_separate(tmp_path):
    application = 'ada-alarm-engine-local'
    composition = build_composition(
        configuration=_configuration(
            volume_path=tmp_path,
            application=application,
            runtime_application=application,
        )
    )

    runtime_current = (
        composition.processor.runtime_root / 'alarms' / 'output' / 'current' / 'latest.json'
    )
    modeler_current = composition.processor.output_root / 'current' / 'latest.json'

    assert composition.processor.runtime_root == tmp_path / application
    assert (
        composition.processor.output_root
        == tmp_path / application / 'alarms' / 'modeler' / 'output'
    )
    assert runtime_current != modeler_current
    assert composition.definition.job_key == 'alarm-modeler'


def test_separate_application_keeps_runtime_source_and_modeler_output_independent(tmp_path):
    runtime_application = 'ada-alarm-engine-local'
    modeler_application = 'ada-alarm-modeler-local'
    composition = build_composition(
        configuration=_configuration(
            volume_path=tmp_path,
            application=modeler_application,
            runtime_application=runtime_application,
        )
    )

    assert composition.processor.runtime_root == tmp_path / runtime_application
    assert composition.processor.output_root == (
        tmp_path / modeler_application / 'alarms' / 'modeler' / 'output'
    )
