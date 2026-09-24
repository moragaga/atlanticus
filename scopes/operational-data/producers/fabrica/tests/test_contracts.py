import pytest

from atlanticus.data_producers.fabrica import (
    FabricaContractError,
    FabricaDatasetDefinition,
    FabricaMetricDefinition,
    FabricaValueKind,
    validate_dataset_catalog,
)


def _metric(key='A', kind=FabricaValueKind.FLOAT):
    return FabricaMetricDefinition(id_kpi=key, metric_key=key.lower(), value_kind=kind)


def test_identical_dataset_configuration_contract_for_plans_and_kpis() -> None:
    for weekly_source in ('7LDB', '7LD'):
        datasets = (
            FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=(_metric(),)),
            FabricaDatasetDefinition(name='weekly', source_value=weekly_source, route_segment='weekly', metrics=(_metric(),)),
        )
        validate_dataset_catalog(datasets=datasets)
        assert datasets[0].metrics == datasets[1].metrics


def test_catalog_rejects_duplicate_source_levels() -> None:
    datasets = (
        FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=()),
        FabricaDatasetDefinition(name='weekly', source_value='day', route_segment='weekly', metrics=()),
    )
    with pytest.raises(FabricaContractError, match='source_value'):
        validate_dataset_catalog(datasets=datasets)


def test_catalog_rejects_inconsistent_shared_metric() -> None:
    datasets = (
        FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=(_metric(),)),
        FabricaDatasetDefinition(name='weekly', source_value='7LD', route_segment='weekly', metrics=(
            FabricaMetricDefinition(id_kpi='A', metric_key='other', value_kind=FabricaValueKind.FLOAT),
        )),
    )
    with pytest.raises(FabricaContractError, match='same metric id'):
        validate_dataset_catalog(datasets=datasets)


def test_float_is_explicit_and_number_is_removed() -> None:
    assert FabricaValueKind.FLOAT == 'float'
    assert 'number' not in tuple(value.value for value in FabricaValueKind)
    assert set(FabricaValueKind) == {
        FabricaValueKind.FLOAT, FabricaValueKind.INTEGER, FabricaValueKind.TEXT,
        FabricaValueKind.BOOLEAN, FabricaValueKind.DATETIME,
    }


def test_dataset_rejects_duplicate_metrics() -> None:
    with pytest.raises(FabricaContractError, match='metric ids'):
        FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=(_metric(), _metric()))
