import json
from datetime import UTC, datetime
from io import BytesIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from atlanticus.connectivity.service_bus import ServiceBusMessage
from atlanticus.connectivity.storage import StorageSasReader
from atlanticus.data_producers.notpii import NotPiiConnector
from atlanticus.data_producers.notpii.materialization import NotPiiMaterializer
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
from atlanticus.integrations.pi.contracts import (
    NotPiiSource,
    PiCatalog,
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
)


def test_shared_tag_and_alias_are_isolated_by_notpii_mode(tmp_path, monkeypatch) -> None:
    catalog = PiCatalog(
        source=NotPiiSource(),
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
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'datasets'))
    reader = StorageSasReader()
    content = b''

    def download_to(*, reference, target):
        target.write(content)
        return len(content)

    monkeypatch.setattr(reader, 'download_to', download_to)
    connector = NotPiiConnector(storage_reader=reader)
    published = {}
    timestamp = datetime(2026, 8, 15, 12, 0, 3, tzinfo=UTC)

    for mode, expected_value in (
        (PiExtractionMode.INTERPOLATED, 1.0),
        (PiExtractionMode.RECORDED, 2.0),
    ):
        stream = BytesIO()
        pq.write_table(
            pa.table(
                {
                    'timestamp': pa.array([pd.Timestamp(timestamp)]),
                    'id_tag': ['TAG_A'],
                    'valor': pa.array([expected_value], type=pa.float64()),
                }
            ),
            stream,
        )
        content = stream.getvalue()
        message = ServiceBusMessage(
            body=json.dumps(
                {
                    'id': f'message-{mode.value}',
                    'url': 'https://storage.example/container/tags.parquet',
                    'SasToken': 'fake-token',
                }
            ).encode(),
            message_id=f'message-{mode.value}',
        )
        batch = connector.read(message=message, catalog=catalog, extraction_mode=mode)
        assert batch.data.columns.to_list() == ['timestamp_utc', 'shared']
        assert batch.data['shared'].to_list() == [expected_value]
        materializer = NotPiiMaterializer(
            runtime=runtime,
            catalog=catalog,
            extraction_mode=mode,
        )
        assert len(materializer.publish(batch)) == 1
        published[mode] = materializer.dataset

    interpolated = published[PiExtractionMode.INTERPOLATED]
    recorded = published[PiExtractionMode.RECORDED]
    assert interpolated.key != recorded.key
    partition = {'year': '2026', 'month': '08', 'day': '15'}
    for mode, expected_value in (
        (PiExtractionMode.INTERPOLATED, 1.0),
        (PiExtractionMode.RECORDED, 2.0),
    ):
        definition = published[mode]
        target = definition.resolve_target(materialization='daily', partition=partition)
        table = runtime.read_table(definition=definition, target=target).table
        assert table.to_pydict() == {
            'timestamp_utc': [timestamp],
            'shared': [expected_value],
        }
