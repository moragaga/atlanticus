from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import atlanticus.data_producers.remanentes.source as source_module
from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConnectionStringCredential,
    StorageSettings,
)
from atlanticus.data_producers.remanentes import RemanentesStorageSource

from .support import build_test_catalog


class _StorageClient(StorageClient):
    def __init__(self, *, download_path: Path) -> None:
        super().__init__(
            settings=StorageSettings(
                credential=StorageConnectionStringCredential('UseDevelopmentStorage=true')
            )
        )
        self.download_path = download_path

    def download_to(self, *, container_name: str, blob_name: str, target) -> int:
        assert container_name == 'dataproduct'
        assert blob_name
        payload = self.download_path.read_bytes()
        target.write(payload)
        return len(payload)


def test_download_closes_parquet_reader_before_removing_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / 'source.parquet'
    pq.write_table(
        pa.table({'stock': ['STOC_2960'], 'ton (KT)': [27]}),
        source_path,
    )
    original_parquet_file = source_module.pq.ParquetFile
    original_unlink = source_module.Path.unlink
    readers: list[object] = []

    class TrackingParquetFile:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._delegate = original_parquet_file(*args, **kwargs)
            readers.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            self._delegate.close()

        def __getattr__(self, name: str):
            return getattr(self._delegate, name)

    def guarded_unlink(path: Path, *args: object, **kwargs: object) -> None:
        assert readers
        assert all(reader.closed for reader in readers)
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(source_module.pq, 'ParquetFile', TrackingParquetFile)
    monkeypatch.setattr(source_module.Path, 'unlink', guarded_unlink)

    source = RemanentesStorageSource(
        client=_StorageClient(download_path=source_path),
        container_name='dataproduct',
        definition=build_test_catalog()[0],
    )

    table = source.download_table(blob_name='source.parquet')

    assert table.column_names == ['STOCK', 'Ton (kt)']
    assert table.num_rows == 1
    assert all(reader.closed for reader in readers)
