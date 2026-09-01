import pytest

from ada.kpis.core import (
    KpiArea,
    KpiCatalog,
    KpiMode,
    KpiSpec,
    KpiValueKind,
    OverKpiSpec,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataSource,
)


def _base(key: str) -> KpiSpec:
    return KpiSpec(
        key=key,
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('signal', DataColumnType.FLOAT),),
    )


def test_over_spec_normalizes_area_and_preserves_declared_dependencies():
    spec = OverKpiSpec(
        key='general.total',
        area=KpiArea.GENERAL,
        dependencies=('general.a', 'general.b'),
        resolver=lambda values: values['general.a'],
        value_kind=KpiValueKind.VALUE,
    )

    assert spec.area is KpiArea.GENERAL
    assert spec.dependencies == ('general.a', 'general.b')
    assert spec.persist_history is False


def test_over_spec_rejects_self_dependency_and_duplicates():
    with pytest.raises(ValueError, match='cannot depend on itself'):
        OverKpiSpec(
            key='general.total',
            area=KpiArea.GENERAL,
            dependencies=('general.total',),
            resolver=lambda values: 1,
        )

    with pytest.raises(ValueError, match='must be unique'):
        OverKpiSpec(
            key='general.total',
            area=KpiArea.GENERAL,
            dependencies=('general.a', 'general.a'),
            resolver=lambda values: 1,
        )


def test_catalog_allows_prior_over_dependency_chain_and_preserves_order():
    first = OverKpiSpec(
        key='general.first',
        area=KpiArea.GENERAL,
        dependencies=('general.base',),
        resolver=lambda values: values['general.base'],
    )
    second = OverKpiSpec(
        key='general.second',
        area=KpiArea.GENERAL,
        dependencies=('general.first',),
        resolver=lambda values: values['general.first'],
    )

    catalog = KpiCatalog((_base('general.base'),), (first, second))

    assert catalog.keys == ('general.base', 'general.first', 'general.second')
    assert catalog.over_specs == (first, second)
    assert len(catalog) == 3


def test_catalog_rejects_future_or_unknown_over_dependency():
    first = OverKpiSpec(
        key='general.first',
        area=KpiArea.GENERAL,
        dependencies=('general.second',),
        resolver=lambda values: 1,
    )
    second = OverKpiSpec(
        key='general.second',
        area=KpiArea.GENERAL,
        dependencies=('general.base',),
        resolver=lambda values: 1,
    )

    with pytest.raises(ValueError, match='base or prior Over KPIs'):
        KpiCatalog((_base('general.base'),), (first, second))


def test_empty_catalog_remains_valid_before_productive_kpis_exist():
    catalog = KpiCatalog(())

    assert len(catalog) == 0
    assert catalog.keys == ()


def test_over_spec_rejects_string_area_even_when_value_matches_enum():
    with pytest.raises(TypeError, match='KpiArea'):
        OverKpiSpec(
            key='general.total',
            area='general',  # type: ignore[arg-type]
            dependencies=('general.base',),
            resolver=lambda values: values['general.base'],
        )
