from datetime import UTC, datetime

from ada.kpis.core import (
    KpiArea,
    KpiMode,
    KpiSpec,
    KpiStatus,
    KpiValueKind,
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


def test_latest_number_returns_ok_and_source_trace() -> None:
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
        decimals=1,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 12.34}]),
        watermark=WATERMARK,
        source_watermarks={VIEW.source: WATERMARK},
        evaluated_at_utc=datetime(2026, 8, 31, 12, 0, 1, tzinfo=UTC),
    )
    assert evaluation.status is KpiStatus.OK
    assert evaluation.parsed_value == 12.3
    assert evaluation.sources[0].watermark == WATERMARK


def test_missing_latest_is_missing_not_error() -> None:
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


def test_sum_aggregates_requested_numeric_columns() -> None:
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
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(daily, [{'a': 1.5, 'b': 2}, {'a': 2.5, 'b': 3}]),
        watermark=WATERMARK,
    )
    assert evaluation.parsed_value == 9.0


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
        persist_history=False,
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1.0}]),
        watermark=WATERMARK,
    )
    assert evaluation.status is KpiStatus.ERROR
    assert evaluation.value_kind is KpiValueKind.JSON
    assert evaluation.error == 'RuntimeError'
    assert 'secret' not in evaluation.to_payload().__repr__()


def test_custom_mapping_is_json_value() -> None:
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
    )
    evaluation = evaluate_kpi(
        spec=spec,
        context=context(VIEW, [{'tag': 1.0}]),
        watermark=WATERMARK,
    )
    assert evaluation.value_kind is KpiValueKind.JSON
    assert evaluation.value == {'value': 1}
