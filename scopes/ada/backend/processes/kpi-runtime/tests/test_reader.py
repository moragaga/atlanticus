from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd
import pyarrow as pa

from ada.processes.kpi_runtime.reader import RoutedDatasetSourceReader
from atlanticus.operational_data.core import DataSource
from atlanticus.operational_data.sources import (
    DataSourceApplications,
    PiSourceProvider,
    build_current_source_registry,
)


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = []

    def scan_dataframe(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(dataframe=pd.DataFrame({'signal': [1.0]}))


def test_reader_routes_only_requested_sources(tmp_path) -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    runtimes: dict[str, FakeRuntime] = {}

    def factory(path):
        runtime = FakeRuntime()
        runtimes[str(path)] = runtime
        return runtime

    reader = RoutedDatasetSourceReader(
        volume_path=tmp_path,
        applications=DataSourceApplications(pi='pi-app'),
        registry=registry,
        sources=(DataSource.PI_INTERPOLATED,),
        runtime_factory=factory,
    )
    binding = registry.get(DataSource.PI_INTERPOLATED)
    target = binding.definition.resolve_target(materialization='latest')

    frame = reader.read_frame(
        definition=binding.definition,
        target=target,
        projection_schema=pa.schema([pa.field('signal', pa.float64())]),
    )

    assert frame['signal'].tolist() == [1.0]
    assert str(tmp_path / 'pi-app' / 'datasets') in runtimes


def test_reader_builds_exact_time_filters(tmp_path) -> None:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    runtime = FakeRuntime()
    reader = RoutedDatasetSourceReader(
        volume_path=tmp_path,
        applications=DataSourceApplications(pi='pi-app'),
        registry=registry,
        sources=(DataSource.PI_INTERPOLATED,),
        runtime_factory=lambda _path: runtime,
    )
    binding = registry.get(DataSource.PI_INTERPOLATED)
    target = binding.definition.resolve_target(
        materialization='daily',
        partition={'year': '2026', 'month': '08', 'day': '31'},
    )
    start = datetime(2026, 8, 31, 19, 0, tzinfo=UTC)
    end = datetime(2026, 8, 31, 20, 0, tzinfo=UTC)

    reader.read_frame(
        definition=binding.definition,
        target=target,
        projection_schema=pa.schema([pa.field('signal', pa.float64())]),
        timestamp_column='timestamp_utc',
        start_utc=start,
        end_utc=end,
    )

    filters = runtime.calls[0]['filters']
    assert len(filters) == 2
    assert filters[0].column == 'timestamp_utc'
    assert filters[0].value == start
    assert filters[1].value == end
