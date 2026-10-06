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
        / 'fabrica_kpis'
        / 'catalog'
        / '_definitions.example.py'
    )

    namespace = run_path(str(example_path))
    metrics = namespace['EXAMPLE_KPI_METRICS']
    datasets = namespace['EXAMPLE_DATASETS']

    validate_dataset_catalog(datasets=datasets)
    assert [(dataset.name, dataset.source_value) for dataset in datasets] == [
        ('daily', 'DAY'),
        ('weekly', '7LD'),
    ]
    assert datasets[0].partition_dimensions == ('year', 'month')
    assert datasets[1].partition_dimensions == ()
    assert all(dataset.metrics == metrics for dataset in datasets)
    assert {metric.value_kind for metric in metrics} == {
        FabricaValueKind.FLOAT,
        FabricaValueKind.BOOLEAN,
    }
