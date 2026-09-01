from datetime import UTC, datetime

import pytest

from ada.kpis.core import (
    KpiEvaluation,
    KpiResult,
    KpiSourceTrace,
    KpiStatus,
    KpiValueKind,
    KpiWatermark,
)
from atlanticus.operational_data.core import DataSource


def watermark() -> KpiWatermark:
    return KpiWatermark(datetime(2026, 8, 31, 12, 0, tzinfo=UTC))


def test_evaluation_round_trip_preserves_source_trace() -> None:
    evaluation = KpiEvaluation(
        key='kpi-a',
        area='general',
        watermark=watermark(),
        evaluated_at_utc=datetime(2026, 8, 31, 12, 0, 1, tzinfo=UTC),
        result=KpiResult(KpiStatus.OK, KpiValueKind.VALUE, 42.0, 42.0),
        sources=(KpiSourceTrace(DataSource.PI_INTERPOLATED, watermark()),),
    )
    assert KpiEvaluation.from_payload(evaluation.to_payload()) == evaluation


def test_error_result_does_not_accept_value_or_raw_detail() -> None:
    with pytest.raises(ValueError, match='must not expose'):
        KpiResult(KpiStatus.ERROR, KpiValueKind.VALUE, value=1, error='ValueError')


def test_missing_result_has_null_value() -> None:
    result = KpiResult(KpiStatus.MISSING, KpiValueKind.VALUE)
    assert result.value is None
    assert result.parsed_value is None
    assert result.error is None


def test_non_finite_value_is_rejected() -> None:
    with pytest.raises(ValueError, match='non-finite'):
        KpiResult(KpiStatus.OK, KpiValueKind.VALUE, value=float('nan'))
