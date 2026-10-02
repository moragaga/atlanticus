from types import SimpleNamespace

from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.data_producers.sql import (
    DataValueKind,
    SqlColumnDefinition,
    SqlLoadStrategy,
    SqlSourceDefinition,
    SqlStorageMode,
)
from atlanticus.kernel import Environment
from atlanticus.operational_data.processes.blockgrade.composition import build_composition


def _configuration(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-blockgrade',
        'VOLUMEN_PATH': str(tmp_path),
        'POLL_INTERVAL_SECONDS': '6.5',
        'SQL_CONNECTION_STRING_BLOCKGRADE': 'Server=localhost;Database=test',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def _catalog() -> tuple[SqlSourceDefinition, ...]:
    return (
        SqlSourceDefinition(
            source_key='test_source',
            source_table='dbo.test_source',
            storage_mode=SqlStorageMode.LATEST,
            load_strategy=SqlLoadStrategy.FULL_SNAPSHOT,
            columns=(
                SqlColumnDefinition(
                    source_name='Id',
                    output_name='id',
                    value_kind=DataValueKind.INTEGER,
                    required=True,
                ),
            ),
        ),
    )


def test_composition_passes_process_identity_to_sql_producer(monkeypatch, tmp_path):
    import atlanticus.operational_data.processes.blockgrade.composition as module

    captured = {}
    sentinel = SimpleNamespace(job=SimpleNamespace(run_iteration=lambda context: None))

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(module, 'build_sql_data_producer', fake_builder)
    composition = build_composition(configuration=_configuration(tmp_path), catalog=_catalog())

    assert composition.definition.sleep_seconds == 6.5
    assert composition.producer is sentinel
    assert captured['producer_key'] == 'blockgrade'
    assert captured['dataset_namespace'] == ('blockgrade',)
    assert captured['missing_scope_fact_name'] == 'missing_shift_ids'
    assert type(captured['scope_provider']).__name__ == 'BlockgradeShiftScopeProvider'
    assert captured['retry_policy'].attempts == 10
    assert captured['retry_policy'].delay_seconds == 5.0


def test_execute_uses_complete_sql_cycle(monkeypatch, tmp_path):
    import atlanticus.operational_data.processes.blockgrade.composition as module

    captured = {}

    def run_cycle(context):
        return None

    sentinel = SimpleNamespace(job=SimpleNamespace(run_cycle=run_cycle))
    expected_result = object()

    def fake_builder(**kwargs):
        return sentinel

    def fake_execute_job(**kwargs):
        captured.update(kwargs)
        return expected_result

    monkeypatch.setattr(module, 'build_sql_data_producer', fake_builder)
    monkeypatch.setattr(module, 'execute_job', fake_execute_job)
    composition = build_composition(configuration=_configuration(tmp_path), catalog=_catalog())

    result = composition.execute(argv=('--run-once',))

    assert result is expected_result
    assert captured['definition'] is composition.definition
    assert captured['iteration'] is run_cycle
    assert captured['argv'] == ('--run-once',)
    assert captured['environ'] is composition.configuration.values
