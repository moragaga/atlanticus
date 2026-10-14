from datetime import UTC, datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from atlanticus.data_producers.remanentes import (
    RemanentesLatestMaterializer,
    RemanentesMaterializer,
    RemanentesSourceBlob,
    RemanentesStorageSource,
)
from atlanticus.data_producers.remanentes.errors import RemanentesContractError
from atlanticus.data_producers.remanentes.materialization import _publication_table
from atlanticus.datasets.core.results import PublicationStatus
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime

from .support import build_test_catalog


@pytest.mark.parametrize('stream_index', (0, 1))
@pytest.mark.parametrize(
    'materializer_type', (RemanentesMaterializer, RemanentesLatestMaterializer)
)
def test_remanentes_publishes_utc_microseconds(
    tmp_path, monkeypatch, stream_index, materializer_type
) -> None:
    definition = build_test_catalog()[stream_index]
    source = object.__new__(RemanentesStorageSource)
    source.definition = definition
    timestamp = datetime(2026, 8, 11, 0, 50, tzinfo=UTC)
    if stream_index == 0:
        source_table = pa.table({'STOCK': ['STOC_2960'], 'Ton (kt)': [27.0]})
    else:
        source_table = pa.table(
            {
                'Fase': ['F11W'],
                'Banco': [3080.0],
                'Tipo de material': ['Mineral'],
                'Observación': ['Actual'],
                'Ton (kt)': [39.0],
            }
        )
    monkeypatch.setattr(source, 'download_table', lambda *, blob_name: source_table)
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))
    materializer = materializer_type(source=source, runtime=runtime, definition=definition)
    blob = RemanentesSourceBlob(
        name='data_20260810_2050.parquet',
        source_file_timestamp_utc=timestamp,
        size=1,
        etag='e1',
        last_modified_utc=timestamp,
    )

    result = materializer.materialize(source_blob=blob)

    assert result.publication.status is PublicationStatus.COMMITTED
    artifacts = tuple(tmp_path.rglob('data.parquet'))
    assert len(artifacts) == 1
    with pq.ParquetFile(artifacts[0]) as parquet:
        assert parquet.schema_arrow.field('timestamp').type == pa.timestamp('us', tz='UTC')
        assert parquet.read()['timestamp'].to_pylist() == [timestamp]
        assert parquet.schema_arrow.field('timestamp').nullable is True


@pytest.mark.parametrize(
    ('value', 'message'),
    (
        ('2026-08-11T00:50:00.000000001Z', 'without data loss'),
        ('2026-08-11T00:50:00.000000999Z', 'without data loss'),
    ),
)
def test_remanentes_rejects_nanoseconds_that_cannot_fit_in_microseconds(value, message) -> None:
    frame = pd.DataFrame({'timestamp': pd.Series(pd.to_datetime([value], utc=True))})

    with pytest.raises(RemanentesContractError, match=message):
        _publication_table(frame)


def test_remanentes_rejects_naive_timestamp() -> None:
    frame = pd.DataFrame({'timestamp': pd.to_datetime(['2026-08-11T00:50:00'])})

    with pytest.raises(RemanentesContractError, match='must be UTC'):
        _publication_table(frame)


def test_remanentes_preserves_additional_column_types() -> None:
    frame = pd.DataFrame(
        {
            'timestamp': pd.to_datetime(['2026-08-11T00:50:00Z'], utc=True),
            'ton_kt': pd.Series([39.0], dtype='Float64'),
            'fase': pd.Series(['F11W'], dtype='string'),
        }
    )
    table = _publication_table(frame)

    assert table.schema.field('timestamp').type == pa.timestamp('us', tz='UTC')
    assert table.schema.field('ton_kt').type == pa.float64()
    assert pa.types.is_string(table.schema.field('fase').type) or pa.types.is_large_string(
        table.schema.field('fase').type
    )
    assert table['fase'].to_pylist() == ['F11W']
    assert table.to_pylist()[0]['timestamp'] == datetime(2026, 8, 11, 0, 50, tzinfo=UTC)
