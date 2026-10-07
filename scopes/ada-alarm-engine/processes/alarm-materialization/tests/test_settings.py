from pathlib import Path

from ada.processes.alarm_materialization.composition import build_composition
from ada.processes.alarm_materialization.settings import configuration_specs
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path: Path, *, disabled: str = 'false') -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-alarm-materialization-test',
        'VOLUMEN_PATH': str(tmp_path),
        'ATLANTICUS_JOB_EXECUTION_DISABLED': disabled,
        'COMMAND_CENTER_COSMOS_ENDPOINT': 'http://localhost:8081',
        'COMMAND_CENTER_COSMOS_KEY': 'local-key',
        'COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command-center',
        'ALARM_CONFIGURATION_CONTAINER_NAME': 'alarm-configuration',
        'ALARM_QUALIFICATIONS_FILE': str(tmp_path / 'qualification.json'),
        'ALARM_MATERIALIZATION_POLL_SECONDS': '30',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
        sensitive_keys=frozenset({'COMMAND_CENTER_COSMOS_KEY'}),
    )


def test_configuration_specs_include_runtime_execution_barrier() -> None:
    specs = {spec.key: spec for spec in configuration_specs()}

    assert specs['ATLANTICUS_JOB_EXECUTION_DISABLED'].default == 'false'


def test_composition_carries_forced_stop_into_runtime_without_opening_cosmos(tmp_path) -> None:
    composition = build_composition(configuration=_configuration(tmp_path, disabled='true'))

    result = composition.execute(argv=[])

    assert composition.runtime_configuration.job_execution_disabled is True
    assert composition.settings.projection_container == 'alarm-configuration'
    assert composition.definition.job_key == 'alarm-materialization'
    assert result.iteration_count == 0
    assert result.stop_reason == 'execution_disabled'
