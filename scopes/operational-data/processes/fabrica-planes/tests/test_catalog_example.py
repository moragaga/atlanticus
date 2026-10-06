from pathlib import Path
from runpy import run_path

from atlanticus.data_producers.fabrica import FabricaValueKind, validate_dataset_catalog


def test_catalog_example_is_valid_and_preserves_dataset_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    example_path = (
        root
        / 'src'
        / 'atlanticus'
        / 'operational_data'
        / 'processes'
        / 'fabrica_planes'
        / 'catalog'
        / '_definitions.example.py'
    )

    namespace = run_path(str(example_path))
    metrics = namespace['PLAN_METRICS']
    datasets = namespace['EXAMPLE_DATASETS']

    validate_dataset_catalog(datasets=datasets)
    assert [(dataset.name, dataset.source_value) for dataset in datasets] == [
        ('daily', 'DAY'),
        ('weekly', '7LDB'),
    ]
    assert len(metrics) == 13
    assert all(dataset.metrics == metrics for dataset in datasets)
    assert all(metric.value_kind is FabricaValueKind.FLOAT for metric in metrics)
