from __future__ import annotations

from datetime import UTC, datetime

from ada.kpis.core import KpiArea, KpiMode, KpiSpec, KpiStatus, KpiValueKind, KpiWatermark
from ada.kpis.evaluation import evaluate_kpi
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    DataSourceView,
)
from tests.support import context

WATERMARK = KpiWatermark(datetime(2026, 8, 31, 12, 0, tzinfo=UTC))
VIEW = DataSourceView(DataSource.PI_INTERPOLATED, DataPartition.LATEST)


def _requirement() -> DataRequirement:
    return DataRequirement(
        source=VIEW.source,
        partition=VIEW.partition,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )


def test_missing_json_uses_declared_empty_structure() -> None:
    spec = KpiSpec(
        key='dynamic',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        source_requirements=(_requirement(),),
        custom_resolver=lambda _context: None,
        value_kind=KpiValueKind.JSON,
        empty_json={'rows': [], 'columns': []},
    )
    result = evaluate_kpi(spec=spec, context=context(VIEW, [{'tag': 1.0}]), watermark=WATERMARK)
    assert result.status is KpiStatus.MISSING
    assert result.value == {'rows': [], 'columns': []}


def test_error_json_uses_declared_empty_structure() -> None:
    def fail(_context):
        raise RuntimeError('detail')

    spec = KpiSpec(
        key='dynamic',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        source_requirements=(_requirement(),),
        custom_resolver=fail,
        value_kind=KpiValueKind.JSON,
        empty_json={'rows': [], 'columns': []},
    )
    result = evaluate_kpi(spec=spec, context=context(VIEW, [{'tag': 1.0}]), watermark=WATERMARK)
    assert result.status is KpiStatus.ERROR
    assert result.value == {'rows': [], 'columns': []}
    assert result.error == 'RuntimeError'
