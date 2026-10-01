from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pyarrow as pa
import pytest

import atlanticus.datasets.parquet._write as write_module
from atlanticus.datasets.parquet import ParquetWriteOptions


def test_parquet_write_fsyncs_the_same_writable_stream_before_closing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_write_table = write_module.pq.write_table
    original_fsync = write_module.os.fsync
    observed: dict[str, object] = {}

    def tracked_write_table(table: pa.Table, where: BinaryIO, **kwargs: object) -> None:
        assert where.writable()
        observed['stream'] = where
        original_write_table(table, where, **kwargs)

    def tracked_fsync(descriptor: int) -> None:
        stream = observed['stream']
        assert hasattr(stream, 'closed')
        assert not stream.closed
        assert stream.writable()
        assert stream.fileno() == descriptor
        observed['fsync_called'] = True
        original_fsync(descriptor)

    monkeypatch.setattr(write_module.pq, 'write_table', tracked_write_table)
    monkeypatch.setattr(write_module.os, 'fsync', tracked_fsync)

    path = tmp_path / 'data.parquet'
    write_module._write_and_validate_table(
        path=path,
        table=pa.table({'value': pa.array([1, 2, 3], type=pa.int64())}),
        write_options=ParquetWriteOptions(),
    )

    stream = observed['stream']
    assert observed['fsync_called'] is True
    assert stream.closed
    assert path.exists()
