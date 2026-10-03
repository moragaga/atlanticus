import pyarrow as pa

from atlanticus.datasets import (
    DatasetDefinition,
    DatasetKey,
    MaterializationDefinition,
    PublicationStatus,
    SingleArtifactLayout,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


def test_runtime_honors_allow_empty_single_artifact(tmp_path) -> None:
    definition = DatasetDefinition(
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
    target = definition.resolve_target(materialization='current')
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))

    result = runtime.replace(
        definition=definition,
        target=target,
        data=pa.table({'value': pa.array([], type=pa.string())}),
    )

    assert result.status is PublicationStatus.COMMITTED
    assert (tmp_path / 'timeseries' / 'current.parquet').is_file()
