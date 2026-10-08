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
        'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'http://localhost:8081',
        'ADA_COMMAND_CENTER_COSMOS_KEY': 'local-key',
        'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command-center',
        'ALARM_MATERIALIZATION_POLL_SECONDS': '30',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
        sensitive_keys=frozenset({'ADA_COMMAND_CENTER_COSMOS_KEY'}),
    )


def test_configuration_specs_include_runtime_execution_barrier() -> None:
    specs = {spec.key: spec for spec in configuration_specs()}

    assert specs['ATLANTICUS_JOB_EXECUTION_DISABLED'].default == 'false'


def test_composition_carries_forced_stop_into_runtime_without_opening_cosmos(tmp_path) -> None:
    composition = build_composition(configuration=_configuration(tmp_path, disabled='true'))

    result = composition.execute(argv=[])

    assert composition.runtime_configuration.job_execution_disabled is True
    assert composition.definition.job_key == 'alarm-materialization'
    assert result.iteration_count == 0
    assert result.stop_reason == 'execution_disabled'


def test_composition_finishes_successfully_after_one_unchanged_iteration(tmp_path) -> None:
    composition = build_composition(configuration=_configuration(tmp_path))
    calls = []

    def unchanged(context):
        calls.append(context)
        context.set_iteration_fact('outcome', 'UNCHANGED')

    composition.job.run_iteration = unchanged

    result = composition.execute(argv=[])

    assert result.iteration_count == 1
    assert result.stop_reason == 'run_once'
    assert len(calls) == 1


def test_materialization_configuration_exposes_no_manual_qualification_or_container() -> None:
    keys = {spec.key for spec in configuration_specs()}
    assert 'ALARM_CONFIGURATION_CONTAINER_NAME' not in keys
    assert 'ALARM_QUALIFICATIONS_FILE' not in keys
    assert 'ADA_COMMAND_CENTER_COSMOS_ENDPOINT' in keys
    assert 'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME' in keys
    assert 'ADA_COMMAND_CENTER_COSMOS_KEY' in keys


def test_azure_preview_extension_builds_for_materialization(tmp_path: Path) -> None:
    from atlanticus.observability import ObservabilitySettings
    from atlanticus.observability_azure import build_azure_observability_extension

    settings = ObservabilitySettings.build(
        application='ada-alarm-materialization-test',
        service='alarm-materialization',
        module='ada.processes.alarm_materialization',
        component='runtime',
        environment=Environment.from_value('local'),
        volume_path=tmp_path,
        file_logs_enabled=True,
    )
    extension = build_azure_observability_extension(
        observability_settings=settings,
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
        },
        volume_path=tmp_path,
    )

    assert extension.enabled is True
