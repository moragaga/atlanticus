from datetime import UTC, datetime

import pyarrow as pa

from atlanticus.datasets.core import (
    DatasetDefinition,
    DatasetKey,
    MaterializationDefinition,
    PublicationStatus,
    SingleArtifactLayout,
)
from atlanticus.datasets.parquet import (
    ColumnFilter,
    FilterOperator,
    ParquetDatasetStore,
)


def _definition() -> DatasetDefinition:
    return DatasetDefinition(
        key=DatasetKey(namespace=('tests',), name='rolling'),
        materializations=(
            MaterializationDefinition(
                name='current',
                layout=SingleArtifactLayout(artifact_name='current', allow_empty=True),
                route_segments=(),
            ),
        ),
        route_segments=('timeseries',),
    )


def test_named_empty_single_artifact_is_committed(tmp_path) -> None:
    definition = _definition()
    target = definition.resolve_target(materialization='current')
    store = ParquetDatasetStore(root=tmp_path)
    schema = pa.schema(
        [pa.field('timestamp_utc', pa.timestamp('us', tz='UTC'), nullable=False)],
        metadata={b'contract': b'rolling'},
    )
    table = pa.Table.from_arrays(
        [pa.array([], type=pa.timestamp('us', tz='UTC'))],
        schema=schema,
    )

    publication = store.replace(definition=definition, target=target, table=table)
    restored = store.read(definition=definition, target=target)

    assert publication.status is PublicationStatus.COMMITTED
    assert (tmp_path / 'timeseries' / 'current.parquet').is_file()
    assert not (tmp_path / 'timeseries' / 'data.parquet').exists()
    assert restored.table.schema.equals(schema, check_metadata=True)
    assert restored.row_count == 0


def test_single_target_scan_preserves_metadata(tmp_path) -> None:
    definition = _definition()
    target = definition.resolve_target(materialization='current')
    store = ParquetDatasetStore(root=tmp_path)
    timestamp = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
    schema = pa.schema(
        [
            pa.field('timestamp_utc', pa.timestamp('us', tz='UTC'), nullable=False),
            pa.field('value', pa.string()),
        ],
        metadata={b'contract': b'rolling'},
    )
    store.replace(
        definition=definition,
        target=target,
        table=pa.Table.from_arrays(
            [
                pa.array([timestamp], type=pa.timestamp('us', tz='UTC')),
                pa.array(['1']),
            ],
            schema=schema,
        ),
    )

    result = store.scan(
        definition=definition,
        targets=(target,),
        columns=('timestamp_utc', 'value'),
        filters=(
            ColumnFilter(
                column='timestamp_utc',
                operator=FilterOperator.LESS_THAN_OR_EQUAL,
                value=timestamp,
            ),
        ),
    )

    assert result.table.schema.metadata == {b'contract': b'rolling'}
