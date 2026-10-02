from datetime import UTC, datetime

import pytest

from ada.kpis.core import (
    KpiEvaluation,
    KpiResult,
    KpiSourceTrace,
    KpiStatus,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
)
from atlanticus.operational_data.core import DataSource


def watermark() -> KpiWatermark:
    return KpiWatermark(datetime(2026, 8, 31, 12, 0, tzinfo=UTC))


def test_evaluation_round_trip_preserves_scalar_type_and_source_trace() -> None:
    evaluation = KpiEvaluation(
        key='kpi-a',
        area='general',
        watermark=watermark(),
        evaluated_at_utc=datetime(2026, 8, 31, 12, 0, 1, tzinfo=UTC),
        result=KpiResult(
            KpiStatus.OK,
            KpiValueKind.VALUE,
            value='42.0',
            parsed_value='42,0',
            value_type=KpiValueType.FLOAT,
        ),
        sources=(KpiSourceTrace(DataSource.PI_INTERPOLATED, watermark()),),
    )
    assert KpiEvaluation.from_payload(evaluation.to_payload()) == evaluation
    assert evaluation.value_type is KpiValueType.FLOAT


def test_value_result_requires_text_representations_and_scalar_type() -> None:
    with pytest.raises(ValueError, match='requires value_type'):
        KpiResult(KpiStatus.MISSING, KpiValueKind.VALUE)
    with pytest.raises(TypeError, match='must be str'):
        KpiResult(
            KpiStatus.OK,
            KpiValueKind.VALUE,
            value=42.0,
            parsed_value='42,0',
            value_type=KpiValueType.FLOAT,
        )


def test_missing_value_result_preserves_declared_type_without_values() -> None:
    result = KpiResult(
        KpiStatus.MISSING,
        KpiValueKind.VALUE,
        value_type=KpiValueType.TEXT,
    )
    assert result.value_type is KpiValueType.TEXT
    assert result.value is None
    assert result.parsed_value is None


def test_json_result_has_no_scalar_type_or_parsed_duplicate() -> None:
    result = KpiResult(KpiStatus.OK, KpiValueKind.JSON, value={'a': 1})
    assert result.value_type is None
    assert result.parsed_value is None
    with pytest.raises(ValueError, match='must not declare value_type'):
        KpiResult(
            KpiStatus.OK,
            KpiValueKind.JSON,
            value={'a': 1},
            value_type=KpiValueType.INTEGER,
        )
