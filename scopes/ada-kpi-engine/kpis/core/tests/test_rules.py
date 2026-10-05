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
    DataInputSpec,
    DataSource,
    DataView,
)


def _input(
    *,
    key: str = 'value',
    view: DataView = DataView.LATEST,
    columns: tuple[DataColumn, ...] | None = None,
) -> DataInputSpec:
    return DataInputSpec(
        input_key=key,
        source=DataSource.PI_INTERPOLATED,
        view=view,
        columns=columns or (DataColumn('tag', DataColumnType.FLOAT),),
    )


def test_simple_spec_owns_one_input_and_infers_float_output() -> None:
    input_spec = _input()
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        inputs=(input_spec,),
        decimals=2,
    )
    assert spec.area is KpiArea.GENERAL
    assert spec.value_kind is KpiValueKind.VALUE
    assert spec.value_type is KpiValueType.FLOAT
    assert spec.is_truncated is True
    assert spec.inputs == (input_spec,)


def test_numeric_defaults_are_zero_decimals_and_truncated() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        inputs=(_input(columns=(DataColumn('tag', DataColumnType.INTEGER),)),),
    )
    assert spec.decimals == 0
    assert spec.is_truncated is True
    assert spec.value_type is KpiValueType.INTEGER


def test_latest_status_can_preserve_boolean_contract() -> None:
    spec = KpiSpec(
        key='enabled',
        area=KpiArea.GENERAL,
        mode=KpiMode.STATUS,
        inputs=(_input(columns=(DataColumn('enabled', DataColumnType.BOOLEAN),)),),
    )
    assert spec.value_type is KpiValueType.BOOLEAN


def test_numeric_mode_rejects_text_column() -> None:
    with pytest.raises(ValueError, match='unsupported column types'):
        KpiSpec(
            key='kpi-a',
            area=KpiArea.GENERAL,
            mode=KpiMode.SUM_LATESTS_NUMBERS,
            inputs=(
                _input(
                    view=DataView.DAILY,
                    columns=(DataColumn('tag', DataColumnType.TEXT),),
                ),
            ),
        )


def test_latest_aggregate_promotes_output_to_float_when_any_column_is_float() -> None:
    spec = KpiSpec(
        key='aggregate',
        area=KpiArea.GENERAL,
        mode=KpiMode.MAX_LATESTS_NUMBERS,
        inputs=(
            _input(
                columns=(
                    DataColumn('a', DataColumnType.INTEGER),
                    DataColumn('b', DataColumnType.FLOAT),
                ),
            ),
        ),
    )
    assert spec.value_type is KpiValueType.FLOAT


def test_simple_kpi_requires_exactly_one_input() -> None:
    with pytest.raises(ValueError, match='exactly one data input'):
        KpiSpec(
            key='none',
            area=KpiArea.GENERAL,
            mode=KpiMode.LATEST_NUMBER,
        )
    with pytest.raises(ValueError, match='exactly one data input'):
        KpiSpec(
            key='many',
            area=KpiArea.GENERAL,
            mode=KpiMode.LATEST_NUMBER,
            inputs=(_input(key='a'), _input(key='b')),
        )


def test_custom_value_requires_explicit_stable_value_type() -> None:
    input_spec = _input()
    with pytest.raises(ValueError, match='requires value_type'):
        KpiSpec(
            key='custom',
            area=KpiArea.GENERAL,
            mode=KpiMode.CUSTOM,
            inputs=(input_spec,),
            custom_resolver=lambda context: 1,
        )
    spec = KpiSpec(
        key='custom',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        inputs=(input_spec,),
        custom_resolver=lambda context: 1,
        value_type=KpiValueType.INTEGER,
    )
    assert spec.inputs == (input_spec,)


def test_custom_inputs_are_named_and_may_share_source_and_view() -> None:
    current = _input(key='current', view=DataView.DAILY)
    previous = _input(key='previous', view=DataView.DAILY)
    spec = KpiSpec(
        key='delta',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        inputs=(current, previous),
        custom_resolver=lambda context: 1,
        value_type=KpiValueType.FLOAT,
    )
    assert tuple(item.input_key for item in spec.inputs) == ('current', 'previous')
    assert {(item.source, item.view) for item in spec.inputs} == {
        (DataSource.PI_INTERPOLATED, DataView.DAILY)
    }


def test_custom_rejects_duplicate_input_keys() -> None:
    with pytest.raises(ValueError, match='input keys must be unique'):
        KpiSpec(
            key='duplicate',
            area=KpiArea.GENERAL,
            mode=KpiMode.CUSTOM,
            inputs=(_input(key='same'), _input(key='same')),
            custom_resolver=lambda context: 1,
            value_type=KpiValueType.FLOAT,
        )


def test_custom_json_has_no_scalar_value_type() -> None:
    spec = KpiSpec(
        key='custom-json',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        inputs=(_input(),),
        custom_resolver=lambda context: {'value': 1},
        value_kind=KpiValueKind.JSON,
    )
    assert spec.value_type is None


def test_constant_scalar_infers_type_without_operational_inputs() -> None:
    spec = KpiSpec(
        key='constant',
        area=KpiArea.GENERAL,
        mode=KpiMode.CONSTANT,
        constant_value=7,
    )
    assert spec.value_type is KpiValueType.INTEGER
    assert spec.inputs == ()


def test_catalog_rejects_duplicate_keys() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        inputs=(_input(),),
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
            inputs=(_input(),),
        )
