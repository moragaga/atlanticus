from __future__ import annotations

import pytest

from atlanticus.connectivity.sql import SqlBatch, SqlResult


def test_result_and_batch_are_neutral_immutable_tuples() -> None:
    result = SqlResult(
        columns=('id', 'value'),
        rows=((1, 'one'), (2, None)),
        duration_ms=1.25,
    )
    batch = SqlBatch(
        columns=result.columns,
        rows=result.rows,
        batch_number=2,
        row_offset=10,
        duration_ms=0.5,
    )

    assert result.row_count == 2
    assert batch.row_count == 2
    assert batch.batch_number == 2
    assert batch.row_offset == 10


@pytest.mark.parametrize(
    'result',
    (
        lambda: SqlResult(columns=(), rows=(), duration_ms=0),
        lambda: SqlResult(columns=('id', ''), rows=(), duration_ms=0),
        lambda: SqlResult(columns=('id',), rows=((1, 2),), duration_ms=0),
        lambda: SqlResult(columns=('id',), rows=(), duration_ms=-1),
        lambda: SqlBatch(columns=('id',), rows=(), batch_number=1, row_offset=0, duration_ms=0),
        lambda: SqlBatch(
            columns=('id',), rows=((1,),), batch_number=0, row_offset=0, duration_ms=0
        ),
        lambda: SqlBatch(
            columns=('id',), rows=((1,),), batch_number=1, row_offset=-1, duration_ms=0
        ),
    ),
)
def test_invalid_result_shapes_are_rejected(result) -> None:
    with pytest.raises(ValueError):
        result()
