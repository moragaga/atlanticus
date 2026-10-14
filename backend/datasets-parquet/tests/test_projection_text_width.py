from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pytest

import atlanticus.datasets.parquet._scan as scan_module
from atlanticus.datasets.core import DatasetDefinition
from atlanticus.datasets.parquet import (
    ParquetCorruptionError,
    ParquetDatasetStore,
    ParquetSchemaError,
)


def _store(tmp_path: Path, clock: datetime) -> ParquetDatasetStore:
    return ParquetDatasetStore(root=tmp_path / 'data', clock=lambda: clock)


def _target(definition: DatasetDefinition, day: str = '21'):
    return definition.resolve_target(
        materialization='granular',
        partition={'year': '2026', 'month': '07', 'day': day},
    )


@pytest.mark.parametrize(
    ('physical', 'requested'),
    ((pa.large_string(), pa.string()), (pa.string(), pa.large_string())),
    ids=('large-to-string', 'string-to-large'),
)
def test_text_projection_converts_utf8_width_safely(
    tmp_path: Path,
    clock: datetime,
    pi_definition: DatasetDefinition,
    physical: pa.DataType,
    requested: pa.DataType,
) -> None:
    store = _store(tmp_path, clock)
    target = _target(pi_definition)
    store.replace(
        definition=pi_definition,
        target=target,
        table=pa.table({
            'fase': pa.array(['FASE 1', 'FASE 2', None], type=physical),
            'tipo_material': pa.array(['Mineral', 'Estéril', None], type=physical),
            'ton_kt': pa.array([1.5, 2.5, None], type=pa.float64()),
        }),
    )
    projection_schema = pa.schema([
        pa.field('fase', requested),
        pa.field('tipo_material', requested),
        pa.field('ton_kt', pa.float64()),
    ])

    result = store.scan(
        definition=pi_definition,
        targets=(target,),
        projection_schema=projection_schema,
    )

    assert result.table.schema.equals(projection_schema)
    assert result.table['fase'].to_pylist() == ['FASE 1', 'FASE 2', None]
    assert result.table['tipo_material'].to_pylist() == ['Mineral', 'Estéril', None]
    assert result.table['ton_kt'].to_pylist() == [1.5, 2.5, None]
    assert store.read_schema(definition=pi_definition, target=target).field('fase').type == physical
    assert store.scan(
        definition=pi_definition,
        targets=(target,),
        columns=('fase',),
    ).table.schema.field('fase').type == physical


@pytest.mark.parametrize('requested', (pa.string(), pa.large_string()))
def test_text_projection_combines_publications_with_different_widths(
    tmp_path: Path,
    clock: datetime,
    pi_definition: DatasetDefinition,
    requested: pa.DataType,
) -> None:
    store = _store(tmp_path, clock)
    first = _target(pi_definition, '20')
    second = _target(pi_definition, '21')
    store.replace(
        definition=pi_definition,
        target=first,
        table=pa.table({'fase': pa.array(['FASE 1'], type=pa.string())}),
    )
    store.replace(
        definition=pi_definition,
        target=second,
        table=pa.table({'fase': pa.array(['FASE 2'], type=pa.large_string())}),
    )

    result = store.scan(
        definition=pi_definition,
        targets=(first, second),
        projection_schema=pa.schema([pa.field('fase', requested)]),
    )

    assert result.table['fase'].type == requested
    assert result.table['fase'].to_pylist() == ['FASE 1', 'FASE 2']
    assert result.target_count == 2


def test_typed_projection_still_rejects_non_text_mismatch(
    tmp_path: Path,
    clock: datetime,
    pi_definition: DatasetDefinition,
) -> None:
    store = _store(tmp_path, clock)
    target = _target(pi_definition)
    store.replace(
        definition=pi_definition,
        target=target,
        table=pa.table({'fase': pa.array([1, 2], type=pa.int64())}),
    )

    with pytest.raises(ParquetSchemaError, match='incompatible type for projected column fase'):
        store.scan(
            definition=pi_definition,
            targets=(target,),
            projection_schema=pa.schema([pa.field('fase', pa.string())]),
        )


def test_text_compatibility_does_not_hide_physical_type_corruption(
    tmp_path: Path,
    clock: datetime,
    pi_definition: DatasetDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path, clock)
    target = _target(pi_definition)
    store.replace(
        definition=pi_definition,
        target=target,
        table=pa.table({'fase': pa.array(['FASE 1'], type=pa.large_string())}),
    )
    monkeypatch.setattr(
        scan_module.pq,
        'read_table',
        lambda *_args, **_kwargs: pa.table({'fase': pa.array(['FASE 1'], type=pa.string())}),
    )

    with pytest.raises(ParquetCorruptionError, match='schema changed while scanning'):
        store.scan(
            definition=pi_definition,
            targets=(target,),
            projection_schema=pa.schema([pa.field('fase', pa.string())]),
        )
