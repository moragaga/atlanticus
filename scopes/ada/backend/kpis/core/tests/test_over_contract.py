import pytest

from ada.kpis.core import (
    KpiArea,
    KpiCatalog,
    KpiMode,
    KpiSpec,
    KpiValueKind,
    KpiValueType,
    OverKpiSpec,
)
from atlanticus.operational_data.core import DataColumn, DataColumnType, DataPartition, DataSource


def _base(key: str) -> KpiSpec:
    return KpiSpec(
        key=key,
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('signal', DataColumnType.FLOAT),),
    )


def _value_over(key: str, dependencies: tuple[str, ...]) -> OverKpiSpec:
    return OverKpiSpec(
        key=key,
        area=KpiArea.GENERAL,
        dependencies=dependencies,
        resolver=lambda values: values[dependencies[0]],
        value_type=KpiValueType.FLOAT,
    )


def test_over_spec_preserves_output_and_precision_contract() -> None:
    spec = OverKpiSpec(
        key='general.total',
        area=KpiArea.GENERAL,
        dependencies=('general.a', 'general.b'),
        resolver=lambda values: values['general.a'],
        value_kind=KpiValueKind.VALUE,
        value_type=KpiValueType.FLOAT,
        decimals=2,
    )
    assert spec.dependencies == ('general.a', 'general.b')
    assert spec.value_type is KpiValueType.FLOAT
    assert spec.decimals == 2
    assert spec.is_truncated is True
    assert spec.persist_history is False


def test_value_over_requires_explicit_type_and_json_forbids_it() -> None:
    with pytest.raises(ValueError, match='requires value_type'):
        OverKpiSpec(
            key='general.total',
            area=KpiArea.GENERAL,
            dependencies=('general.a',),
            resolver=lambda values: 1,
        )
    with pytest.raises(ValueError, match='must not declare value_type'):
        OverKpiSpec(
            key='general.payload',
            area=KpiArea.GENERAL,
            dependencies=('general.a',),
            resolver=lambda values: {'a': 1},
            value_kind=KpiValueKind.JSON,
            value_type=KpiValueType.FLOAT,
        )


def test_over_spec_rejects_self_dependency_and_duplicates() -> None:
    with pytest.raises(ValueError, match='cannot depend on itself'):
        _value_over('general.total', ('general.total',))
    with pytest.raises(ValueError, match='must be unique'):
        _value_over('general.total', ('general.a', 'general.a'))


def test_catalog_allows_prior_over_dependency_chain_and_preserves_order() -> None:
    first = _value_over('general.first', ('general.base',))
    second = _value_over('general.second', ('general.first',))
    catalog = KpiCatalog((_base('general.base'),), (first, second))
    assert catalog.keys == ('general.base', 'general.first', 'general.second')
    assert catalog.over_specs == (first, second)
    assert len(catalog) == 3


def test_catalog_rejects_future_or_unknown_over_dependency() -> None:
    first = _value_over('general.first', ('general.second',))
    second = _value_over('general.second', ('general.base',))
    with pytest.raises(ValueError, match='base or prior Over KPIs'):
        KpiCatalog((_base('general.base'),), (first, second))


def test_empty_catalog_remains_valid_before_productive_kpis_exist() -> None:
    catalog = KpiCatalog(())
    assert len(catalog) == 0
    assert catalog.keys == ()
