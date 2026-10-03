from __future__ import annotations

from datetime import UTC, datetime

import pyarrow as pa
import pytest

from atlanticus.datasets import (
    DatasetDefinition,
    DatasetKey,
    FileSetLayout,
    MaterializationDefinition,
    SingleArtifactLayout,
)
from atlanticus.datasets.parquet import ParquetPart


@pytest.fixture
def clock() -> datetime:
    return datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def pi_definition() -> DatasetDefinition:
    return DatasetDefinition(
        key=DatasetKey(namespace=('pi', 'pi-web-api', 'recorded'), name='process'),
        materializations=(
            MaterializationDefinition(
                name='granular',
                layout=SingleArtifactLayout(),
                partition_dimensions=('year', 'month', 'day'),
            ),
        ),
    )


@pytest.fixture
def dispatch_definition() -> DatasetDefinition:
    return DatasetDefinition(
        key=DatasetKey(namespace=('dispatch',), name='shift-dumps'),
        materializations=(
            MaterializationDefinition(
                name='operational-day',
                layout=FileSetLayout(part_dimension='shift_id'),
                partition_dimensions=('year', 'month', 'day'),
            ),
        ),
    )


@pytest.fixture
def timestamp_array():
    def build(*values: str) -> pa.Array:
        parsed = tuple(datetime.fromisoformat(value.replace('Z', '+00:00')) for value in values)
        return pa.array(parsed, type=pa.timestamp('us', tz='UTC'))

    return build


@pytest.fixture
def dispatch_target(dispatch_definition: DatasetDefinition):
    return dispatch_definition.resolve_target(
        materialization='operational-day',
        partition={'year': '2026', 'month': '07', 'day': '21'},
    )


@pytest.fixture
def dispatch_part(dispatch_definition: DatasetDefinition, dispatch_target):
    def build(*, shift_id: str, tonnage: tuple[float, ...]) -> ParquetPart:
        return ParquetPart(
            key=dispatch_definition.resolve_part(target=dispatch_target, value=shift_id),
            table=pa.table(
                {
                    'shift_id': pa.array([int(shift_id)] * len(tonnage), type=pa.int64()),
                    'equipment': pa.array([f'TRUCK-{index + 1}' for index in range(len(tonnage))]),
                    'tonnage': pa.array(tonnage, type=pa.float64()),
                }
            ),
        )

    return build
