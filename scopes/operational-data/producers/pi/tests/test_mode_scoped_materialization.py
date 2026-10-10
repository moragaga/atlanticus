from datetime import UTC, datetime

from atlanticus.data_producers.pi import (
    PiAcquisitionResult,
    PiAcquisitionWindow,
    PiDataProducerMaterializer,
    PiSample,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
from atlanticus.integrations.pi.contracts import (
    PiCatalog,
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
    PiWebApiSource,
)
from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration


def test_identical_tag_and_alias_publish_separate_mode_datasets(tmp_path) -> None:
    catalog = PiCatalog(
        source=PiWebApiSource(interpolation_seconds=10),
        definitions=(
            PiTagDefinition(
                tag_name='TAG_A',
                alias='shared',
                value_kind=PiValueKind.FLOAT,
                extraction_mode=PiExtractionMode.INTERPOLATED,
                materializations=(PiMaterialization.DAILY,),
            ),
            PiTagDefinition(
                tag_name='TAG_A',
                alias='shared',
                value_kind=PiValueKind.FLOAT,
                extraction_mode=PiExtractionMode.RECORDED,
                materializations=(PiMaterialization.DAILY,),
            ),
        ),
    )
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'ada' / 'datasets'))
    materializer = PiDataProducerMaterializer(runtime=runtime, catalog=catalog)
    slot = datetime(2026, 8, 15, 10, 0, 0, tzinfo=UTC)
    recorded_time = datetime(2026, 8, 15, 10, 0, 3, tzinfo=UTC)
    window = PiAcquisitionWindow(
        first_slot_utc=slot,
        last_slot_utc=slot,
        interpolation_seconds=10,
    )
    configuration = RuntimeConfiguration.from_sources(
        environ={
            'ENVIRONMENT': 'local',
            'APPLICATION': 'ada',
            'VOLUMEN_PATH': str(tmp_path),
        }
    )
    context = JobRuntimeContext.create(
        definition=JobDefinition(
            module_name='tests.pi_mode_scoped',
            service_name='pi-web-api',
            execution_timeout_seconds=30,
            shutdown_grace_seconds=1,
            iteration_timeout_seconds=10,
        ),
        configuration=configuration,
        run_id='run-id',
        correlation_id='correlation-id',
    )
    context._begin_iteration(1)

    result = materializer.publish(
        window=window,
        acquisition=PiAcquisitionResult(
            interpolated=(PiSample('TAG_A', slot, 1.0),),
            recorded=(PiSample('TAG_A', recorded_time, 2.0),),
        ),
        context=context,
    )

    assert len(result.publications) == 2
    partition = {'year': '2026', 'month': '08', 'day': '15'}
    interpolated = materializer.dataset_for(PiExtractionMode.INTERPOLATED)
    recorded = materializer.dataset_for(PiExtractionMode.RECORDED)
    assert interpolated is not None
    assert recorded is not None
    assert interpolated.key != recorded.key
    for definition, expected_time, expected_value in (
        (interpolated, slot, 1.0),
        (recorded, recorded_time, 2.0),
    ):
        target = definition.resolve_target(materialization='daily', partition=partition)
        table = runtime.read_table(definition=definition, target=target).table
        assert table.to_pydict() == {
            'timestamp_utc': [expected_time],
            'shared': [expected_value],
        }
