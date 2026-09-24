import re

from atlanticus.connectivity.storage import StorageSasCredential, StorageSettings
from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaMetricDefinition,
    FabricaStorageConnection,
    FabricaStreamDefinition,
    FabricaValueKind,
    build_fabrica_data_producer,
)
from atlanticus.kernel import Environment
from atlanticus.runtime import RuntimeConfiguration


def _connection(container):
    return FabricaStorageConnection(
        settings=StorageSettings(credential=StorageSasCredential(
            account_url='https://example.blob.core.windows.net', sas_token='sv=1',
        )), container_name=container,
    )


def _definition(name, metrics):
    return FabricaStreamDefinition(
        stream_key=name, source_prefix=name,
        source_filename_pattern=re.compile(r'input_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment=name,
        datasets=(FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=metrics),),
    )


def test_single_stream_does_not_require_other_fabrica_storage(tmp_path) -> None:
    definitions = (_definition('planes', (
        FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT),
    )),)
    components = build_fabrica_data_producer(
        runtime_configuration=RuntimeConfiguration(environment=Environment.from_value('local'), application='planes-app', volume_path=tmp_path),
        definitions=definitions, connections={'planes': _connection('plans')}, idle_seconds=5,
        producer_key='fabrica-planes',
    )
    assert set(components.storages) == {'planes'}
    assert tuple(item.definition.stream_key for item in components.materializers) == ('planes',)


def test_disabled_metrics_do_not_trigger_storage_or_materialization(tmp_path) -> None:
    components = build_fabrica_data_producer(
        runtime_configuration=RuntimeConfiguration(environment=Environment.from_value('local'), application='kpis-app', volume_path=tmp_path),
        definitions=(_definition('kpis', ()),), connections={'kpis': _connection('kpis')}, idle_seconds=5,
    )
    assert components.storages == {}
    assert components.materializers == ()
