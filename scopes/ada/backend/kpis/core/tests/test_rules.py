from datetime import UTC, datetime

import pytest

from ada.kpis.core import (
    KpiArea,
    KpiCatalog,
    KpiMode,
    KpiSpec,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
)


def test_simple_spec_projects_typed_requirement_and_infers_float_output() -> None:
    column = DataColumn('tag', DataColumnType.FLOAT)
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(column,),
        decimals=2,
    )
    assert spec.area is KpiArea.GENERAL
    assert spec.value_kind is KpiValueKind.VALUE
    assert spec.value_type is KpiValueType.FLOAT
    assert spec.is_truncated is True
    assert spec.requirements == (
        DataRequirement(
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.LATEST,
            columns=(column,),
        ),
    )


def test_numeric_defaults_are_zero_decimals_and_truncated() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('tag', DataColumnType.INTEGER),),
    )
    assert spec.decimals == 0
    assert spec.is_truncated is True
    assert spec.value_type is KpiValueType.INTEGER


def test_latest_status_can_preserve_boolean_contract() -> None:
    spec = KpiSpec(
        key='enabled',
        area=KpiArea.GENERAL,
        mode=KpiMode.STATUS,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('enabled', DataColumnType.BOOLEAN),),
    )
    assert spec.value_type is KpiValueType.BOOLEAN


def test_numeric_mode_rejects_text_column() -> None:
    with pytest.raises(ValueError, match='unsupported column types'):
        KpiSpec(
            key='kpi-a',
            area=KpiArea.GENERAL,
            mode=KpiMode.SUM_LATESTS_NUMBERS,
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.DAILY,
            columns=(DataColumn('tag', DataColumnType.TEXT),),
        )


def test_latest_aggregate_promotes_output_to_float_when_any_column_is_float() -> None:
    spec = KpiSpec(
        key='aggregate',
        area=KpiArea.GENERAL,
        mode=KpiMode.MAX_LATESTS_NUMBERS,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(
            DataColumn('a', DataColumnType.INTEGER),
            DataColumn('b', DataColumnType.FLOAT),
        ),
    )
    assert spec.value_type is KpiValueType.FLOAT


def test_custom_value_requires_explicit_stable_value_type() -> None:
    requirement = DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )
    with pytest.raises(ValueError, match='requires value_type'):
        KpiSpec(
            key='custom',
            area=KpiArea.GENERAL,
            mode=KpiMode.CUSTOM,
            source_requirements=(requirement,),
            custom_resolver=lambda context: 1,
        )
    spec = KpiSpec(
        key='custom',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        source_requirements=(requirement,),
        custom_resolver=lambda context: 1,
        value_type=KpiValueType.INTEGER,
    )
    assert spec.requirements == (requirement,)


def test_custom_json_has_no_scalar_value_type() -> None:
    requirement = DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )
    spec = KpiSpec(
        key='custom-json',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        source_requirements=(requirement,),
        custom_resolver=lambda context: {'value': 1},
        value_kind=KpiValueKind.JSON,
    )
    assert spec.value_type is None


def test_constant_scalar_infers_type_without_operational_requirements() -> None:
    spec = KpiSpec(
        key='constant',
        area=KpiArea.GENERAL,
        mode=KpiMode.CONSTANT,
        constant_value=7,
    )
    assert spec.value_type is KpiValueType.INTEGER
    assert spec.requirements == ()


def test_catalog_rejects_duplicate_keys() -> None:
    column = DataColumn('tag', DataColumnType.FLOAT)
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(column,),
    )
    with pytest.raises(ValueError, match='unique'):
        KpiCatalog((spec, spec))


def test_watermark_requires_second_precision() -> None:
    with pytest.raises(ValueError, match='second precision'):
        KpiWatermark(datetime(2026, 8, 31, 12, 0, 0, 1, tzinfo=UTC))


def test_spec_rejects_string_area_even_when_value_matches_enum() -> None:
    with pytest.raises(TypeError, match='KpiArea'):
        KpiSpec(
            key='kpi-a',
            area='general',  # type: ignore[arg-type]
            mode=KpiMode.LATEST_NUMBER,
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.LATEST,
            columns=(DataColumn('tag', DataColumnType.FLOAT),),
        )
