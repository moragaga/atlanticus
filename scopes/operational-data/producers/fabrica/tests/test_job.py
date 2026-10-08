import re
from datetime import UTC, datetime
from types import SimpleNamespace

from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaJob,
    FabricaMaterializationResult,
    FabricaMaterializer,
    FabricaMetricDefinition,
    FabricaProducerState,
    FabricaSourceBlob,
    FabricaStreamDefinition,
    FabricaValueKind,
)
from atlanticus.state import AtomicStateStore


class _Logger:
    def __init__(self):
        self.warnings = []

    def debug(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def exception(self, *_args, **_kwargs):
        return None

    def warning(self, message, **fields):
        self.warnings.append((message, fields))


class _Context:
    def __init__(self):
        self.configuration = SimpleNamespace(environment=SimpleNamespace(is_local=True))
        self.iteration_has_work = False
        self.execution_facts = {}
        self.iteration_facts = {}
        self.execution_counters = {}
        self.logger = _Logger()

    def get_execution_fact(self, name):
        return self.execution_facts.get(name)

    def set_execution_fact(self, name, value):
        self.execution_facts[name] = value

    def set_iteration_fact(self, name, value):
        self.iteration_facts[name] = value

    def mark_iteration_work(self):
        self.iteration_has_work = True

    def increment_execution_counter(self, name, amount=1):
        self.execution_counters[name] = self.execution_counters.get(name, 0) + amount


def test_empty_catalog_is_noop_without_storage(tmp_path) -> None:
    state = FabricaProducerState(
        store=AtomicStateStore(volume_path=tmp_path, application='fabrica-planes')
    )
    context = _Context()
    job = FabricaJob(materializers=(), producer_state=state, idle_seconds=5)
    job.run_iteration(context)
    assert context.iteration_facts['streams_planned'] == 0
    assert context.iteration_facts['partitions_changed'] == 0
    assert context.iteration_facts['outcome'] == 'skipped'


class _Materializer(FabricaMaterializer):
    def __init__(self, definition, source_blob, result):
        self.definition = definition
        self._source_blob = source_blob
        self._result = result

    @property
    def catalog_signature(self):
        return 'sha256:test'

    def latest_source(self, *, prefix):
        return self._source_blob

    def materialize(self, *, source_blob):
        assert source_blob == self._source_blob
        return self._result


def test_extra_source_values_do_not_generate_warnings(tmp_path) -> None:
    metric = FabricaMetricDefinition(
        id_kpi='A',
        metric_key='a',
        value_kind=FabricaValueKind.FLOAT,
    )
    definition = FabricaStreamDefinition(
        stream_key='planes',
        source_prefix='planes',
        source_filename_pattern=re.compile(r'planes_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='planes',
        datasets=(
            FabricaDatasetDefinition(
                name='daily',
                source_value='DAY',
                route_segment='daily',
                metrics=(metric,),
                partition_dimensions=('year', 'month'),
            ),
            FabricaDatasetDefinition(
                name='weekly',
                source_value='7LDB',
                route_segment='weekly',
                metrics=(metric,),
                partition_dimensions=('year', 'month'),
            ),
        ),
    )
    source_blob = FabricaSourceBlob(
        name='planes_20261007010000.parquet',
        source_file_timestamp_utc=datetime(2026, 10, 7, 1, tzinfo=UTC),
        size=10,
        etag='etag',
        last_modified_utc=None,
    )
    result = FabricaMaterializationResult(
        source_blob=source_blob,
        source_row_count=1,
        publications=(),
        unknown_source_values=('HOUR',),
        metrics_expected=2,
        metrics_present=1,
        missing_metric_keys=(),
        missing_metric_keys_by_output=(),
    )
    state = FabricaProducerState(
        store=AtomicStateStore(volume_path=tmp_path, application='fabrica-planes')
    )
    job = FabricaJob(
        materializers=(_Materializer(definition, source_blob, result),),
        producer_state=state,
        idle_seconds=5,
    )
    context = _Context()

    job.run_iteration(context)

    assert context.iteration_facts['streams_completed'] == 1
    assert context.iteration_facts['streams_failed'] == 0
    assert context.logger.warnings == []


def test_kpi_source_mismatch_warning_includes_kpi_and_available_sources(tmp_path) -> None:
    metric = FabricaMetricDefinition(
        id_kpi='TEST_KPI_A',
        metric_key='test_kpi_a',
        value_kind=FabricaValueKind.FLOAT,
    )
    definition = FabricaStreamDefinition(
        stream_key='planes',
        source_prefix='planes',
        source_filename_pattern=re.compile(r'planes_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='planes',
        datasets=(
            FabricaDatasetDefinition(
                name='daily',
                source_value='DAY',
                route_segment='daily',
                metrics=(metric,),
            ),
        ),
    )
    source_blob = FabricaSourceBlob(
        name='planes_20261008010000.parquet',
        source_file_timestamp_utc=datetime(2026, 10, 8, 1, tzinfo=UTC),
        size=10,
        etag='etag',
        last_modified_utc=None,
    )
    result = FabricaMaterializationResult(
        source_blob=source_blob,
        source_row_count=0,
        publications=(),
        unknown_source_values=(),
        metrics_expected=1,
        metrics_present=0,
        missing_metric_keys=('test_kpi_a',),
        missing_metric_keys_by_output=(('daily', ('test_kpi_a',)),),
        source_mismatches=(('TEST_KPI_A', 'test_kpi_a', 'daily', 'DAY', ('MTD', 'YTD')),),
    )
    state = FabricaProducerState(
        store=AtomicStateStore(volume_path=tmp_path, application='fabrica-planes')
    )
    job = FabricaJob(
        materializers=(_Materializer(definition, source_blob, result),),
        producer_state=state,
        idle_seconds=5,
    )
    context = _Context()

    job.run_iteration(context)

    assert context.iteration_facts['streams_completed'] == 1
    assert context.iteration_facts['streams_failed'] == 0
    assert context.logger.warnings == [
        (
            'KPI source mismatch',
            {
                'event_name': 'fabrica.stream.kpi_source_mismatch',
                'stream': 'planes',
                'id_kpi': 'TEST_KPI_A',
                'metric_key': 'test_kpi_a',
                'dataset': 'daily',
                'expected_source': 'DAY',
                'available_sources': 'MTD,YTD',
            },
        )
    ]


def test_missing_kpi_warns_once_without_failing_materialization(tmp_path) -> None:
    metric = FabricaMetricDefinition(
        id_kpi='TEST_KEY', metric_key='test_key', value_kind=FabricaValueKind.FLOAT
    )
    definition = FabricaStreamDefinition(
        stream_key='planes',
        source_prefix='planes',
        source_filename_pattern=re.compile(r'planes_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='planes',
        datasets=(
            FabricaDatasetDefinition(
                name='daily', source_value='DAY', route_segment='daily', metrics=(metric,)
            ),
            FabricaDatasetDefinition(
                name='weekly', source_value='7LDB', route_segment='weekly', metrics=(metric,)
            ),
        ),
    )
    source_blob = FabricaSourceBlob(
        name='planes_20261008010000.parquet',
        source_file_timestamp_utc=datetime(2026, 10, 8, 1, tzinfo=UTC),
        size=10,
        etag='etag',
        last_modified_utc=None,
    )
    result = FabricaMaterializationResult(
        source_blob=source_blob,
        source_row_count=0,
        publications=(),
        unknown_source_values=(),
        metrics_expected=2,
        metrics_present=0,
        missing_metric_keys=('test_key',),
        missing_metric_keys_by_output=(('daily', ('test_key',)), ('weekly', ('test_key',))),
        missing_source_kpis=(('TEST_KEY', 'test_key', ('DAY', '7LDB')),),
    )
    state = FabricaProducerState(
        store=AtomicStateStore(volume_path=tmp_path, application='fabrica-planes')
    )
    job = FabricaJob(
        materializers=(_Materializer(definition, source_blob, result),),
        producer_state=state,
        idle_seconds=5,
    )
    context = _Context()

    job.run_iteration(context)

    assert context.iteration_facts['streams_completed'] == 1
    assert context.iteration_facts['streams_failed'] == 0
    assert context.logger.warnings == [
        (
            'KPI missing from source',
            {
                'event_name': 'fabrica.stream.kpi_missing_from_source',
                'stream': 'planes',
                'id_kpi': 'TEST_KEY',
                'metric_key': 'test_key',
                'expected_sources': 'DAY,7LDB',
            },
        ),
    ]
