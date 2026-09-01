from datetime import UTC, datetime

from ada.kpis.core import (
    KpiArea,
    KpiMode,
    KpiSpec,
    KpiStatus,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
)
from ada.kpis.evaluation import evaluate_kpi
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    DataSourceView,
    TimeWindow,
    TimeWindowUnit,
)
from tests.support import context

WATERMARK = KpiWatermark(datetime(2026, 8, 31, 12, 0, tzinfo=UTC))
VIEW = DataSourceView(DataSource.PI_INTERPOLATED, DataPartition.LATEST)


def test_float_contract_truncates_both_representations_and_formats_only_parsed() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
        decimals=2,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1234.29678}]),
        watermark=WATERMARK,
        source_watermarks={VIEW.source: WATERMARK},
        evaluated_at_utc=datetime(2026, 8, 31, 12, 0, 1, tzinfo=UTC),
    )
    assert evaluation.status is KpiStatus.OK
    assert evaluation.value_type is KpiValueType.FLOAT
    assert evaluation.value == '1234.29'
    assert evaluation.parsed_value == '1.234,29'
    assert evaluation.sources[0].watermark == WATERMARK


def test_is_truncated_false_preserves_precision_in_both_formats() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
        decimals=2,
        is_truncated=False,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1234.29678}]),
        watermark=WATERMARK,
    )
    assert evaluation.value == '1234.29678'
    assert evaluation.parsed_value == '1.234,29678'


def test_text_one_remains_text_and_is_never_inferred_as_number_or_boolean() -> None:
    spec = KpiSpec(
        key='state',
        area=KpiArea.GENERAL,
        mode=KpiMode.STATUS,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.TEXT),),
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': '1'}]),
        watermark=WATERMARK,
    )
    assert evaluation.value_type is KpiValueType.TEXT
    assert evaluation.value == '1'
    assert evaluation.parsed_value == '1'


def test_integer_uses_neutral_value_and_chilean_grouping() -> None:
    spec = KpiSpec(
        key='count',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.INTEGER),),
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1234}]),
        watermark=WATERMARK,
    )
    assert evaluation.value_type is KpiValueType.INTEGER
    assert evaluation.value == '1234'
    assert evaluation.parsed_value == '1.234'


def test_missing_latest_preserves_expected_scalar_type() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.TEXT),),
    )
    evaluation = evaluate_kpi(spec=spec, context=context(VIEW, []), watermark=WATERMARK)
    assert evaluation.status is KpiStatus.MISSING
    assert evaluation.value_type is KpiValueType.TEXT


def test_sum_latest_numbers_aggregates_only_latest_value_of_each_column() -> None:
    daily = DataSourceView(DataSource.PI_INTERPOLATED, DataPartition.DAILY)
    spec = KpiSpec(
        key='sum-latest',
        area=KpiArea.GENERAL,
        mode=KpiMode.SUM_LATESTS_NUMBERS,
        source=daily.source,
        partition=daily.partition,
        columns=(
            DataColumn('a', DataColumnType.FLOAT),
            DataColumn('b', DataColumnType.INTEGER),
        ),
        time_window=TimeWindow(1, TimeWindowUnit.DAYS),
        decimals=1,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(daily, [{'a': 1.5, 'b': 2}, {'a': 2.5, 'b': 3}]),
        watermark=WATERMARK,
    )
    assert evaluation.value == '5.5'
    assert evaluation.parsed_value == '5,5'


def test_existing_sum_mode_keeps_all_rows_semantic() -> None:
    daily = DataSourceView(DataSource.PI_INTERPOLATED, DataPartition.DAILY)
    spec = KpiSpec(
        key='sum',
        area=KpiArea.GENERAL,
        mode=KpiMode.SUM,
        source=daily.source,
        partition=daily.partition,
        columns=(
            DataColumn('a', DataColumnType.FLOAT),
            DataColumn('b', DataColumnType.INTEGER),
        ),
        time_window=TimeWindow(1, TimeWindowUnit.DAYS),
        decimals=1,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(daily, [{'a': 1.5, 'b': 2}, {'a': 2.5, 'b': 3}]),
        watermark=WATERMARK,
    )
    assert evaluation.value == '9.0'


def test_constant_scalar_is_evaluated_without_source_requirements() -> None:
    spec = KpiSpec(
        key='constant',
        area=KpiArea.GENERAL,
        mode=KpiMode.CONSTANT,
        constant_value=12.987,
        decimals=2,
    )
    evaluation = evaluate_kpi(spec=spec, context=context(VIEW, []), watermark=WATERMARK)
    assert evaluation.value_type is KpiValueType.FLOAT
    assert evaluation.value == '12.98'
    assert evaluation.parsed_value == '12,98'
    assert evaluation.sources == ()


def test_custom_exception_is_sanitized_to_exception_type() -> None:
    requirement = DataRequirement(
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )

    def fail(_context):
        raise RuntimeError('secret detail')

    spec = KpiSpec(
        key='custom',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        source_requirements=(requirement,),
        custom_resolver=fail,
        value_kind=KpiValueKind.JSON,
        persist_history=False,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1.0}]),
        watermark=WATERMARK,
    )
    assert evaluation.status is KpiStatus.ERROR
    assert evaluation.value_kind is KpiValueKind.JSON
    assert evaluation.value_type is None
    assert evaluation.error == 'RuntimeError'
    assert 'secret' not in evaluation.to_payload().__repr__()


def test_custom_mapping_is_json_without_parsed_duplicate() -> None:
    requirement = DataRequirement(
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )
    spec = KpiSpec(
        key='custom',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        source_requirements=(requirement,),
        custom_resolver=lambda _context: {'value': 1},
        value_kind=KpiValueKind.JSON,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1.0}]),
        watermark=WATERMARK,
    )
    assert evaluation.value_kind is KpiValueKind.JSON
    assert evaluation.value_type is None
    assert evaluation.value == {'value': 1}
    assert evaluation.parsed_value is None


def test_truncated_precision_keeps_declared_decimal_places() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
        decimals=2,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 4.2}]),
        watermark=WATERMARK,
    )
    assert evaluation.value == '4.20'
    assert evaluation.parsed_value == '4,20'
