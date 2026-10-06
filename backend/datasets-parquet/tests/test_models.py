from __future__ import annotations

import pyarrow as pa

from atlanticus.datasets.core import (
    DatasetDefinition,
    DatasetKey,
    MaterializationDefinition,
    SingleArtifactLayout,
)
from atlanticus.datasets.parquet import ParquetReadResult


def test_read_result_is_isolated_from_mutable_collection_inputs() -> None:
    definition = DatasetDefinition(
        key=DatasetKey(namespace=('test',), name='dataset'),
        materializations=(
            MaterializationDefinition(
                name='daily',
                layout=SingleArtifactLayout(),
                partition_dimensions=('day',),
            ),
        ),
    )
    target = definition.resolve_target(
        materialization='daily',
        partition={'day': '2026-08-12'},
    )
    targets = [target]
    publication_tokens = ['token-1']
    warnings = ['warning-1']

    result = ParquetReadResult(
        table=pa.table({'value': [1]}),
        targets=targets,
        artifact_count=1,
        size_bytes=1,
        publication_tokens=publication_tokens,
        warnings=warnings,
    )

    targets.clear()
    publication_tokens.append('token-2')
    warnings.clear()

    assert list(result.targets) == [target]
    assert list(result.publication_tokens) == ['token-1']
    assert list(result.warnings) == ['warning-1']
