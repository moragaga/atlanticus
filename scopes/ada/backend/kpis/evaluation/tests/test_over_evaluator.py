from datetime import UTC, datetime

import pytest

from ada.kpis.core import (
    KpiArea,
    KpiEvaluation,
    KpiResult,
    KpiSourceTrace,
    KpiStatus,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
    OverKpiSpec,
)
from ada.kpis.evaluation import KpiDependencies, KpiDependencyNotRequestedError, evaluate_over_kpi
from atlanticus.operational_data.core import DataSource

WATERMARK = KpiWatermark(datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
EVALUATED_AT = datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC)


def _evaluation(
    key: str,
    *,
    status: KpiStatus = KpiStatus.OK,
    value='10.0',
    value_type: KpiValueType = KpiValueType.FLOAT,
    source: DataSource = DataSource.PI_INTERPOLATED,
) -> KpiEvaluation:
    if status is KpiStatus.ERROR:
        result = KpiResult(
            KpiStatus.ERROR,
            KpiValueKind.VALUE,
            error='RuntimeError',
            value_type=value_type,
        )
    elif status is KpiStatus.MISSING:
        result = KpiResult(KpiStatus.MISSING, KpiValueKind.VALUE, value_type=value_type)
    else:
        result = KpiResult(
            KpiStatus.OK,
            KpiValueKind.VALUE,
            value=value,
            parsed_value=value.replace('.', ','),
            value_type=value_type,
        )
    return KpiEvaluation(
        key=key,
        area='general',
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
        result=result,
        sources=(KpiSourceTrace(source, WATERMARK),),
    )


def test_dependencies_reject_access_to_undeclared_key() -> None:
    values = KpiDependencies({'general.a': 1})
    with pytest.raises(KpiDependencyNotRequestedError):
        _ = values['general.b']


def test_over_evaluation_decodes_dependencies_and_applies_same_precision_to_both_outputs() -> None:
    spec = OverKpiSpec(
        key='general.ratio',
        area=KpiArea.GENERAL,
        dependencies=('general.a', 'general.b'),
        resolver=lambda values: values['general.a'] / values['general.b'],
        value_type=KpiValueType.FLOAT,
        decimals=2,
        persist_history=True,
    )
    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={
            'general.a': _evaluation('general.a', value='1234.29678'),
            'general.b': _evaluation('general.b', value='1.0'),
        },
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )
    assert evaluation.status is KpiStatus.OK
    assert evaluation.value == '1234.29'
    assert evaluation.parsed_value == '1.234,29'
    assert evaluation.value_type is KpiValueType.FLOAT
    assert evaluation.persist_history is True
    assert evaluation.sources == (KpiSourceTrace(DataSource.PI_INTERPOLATED, WATERMARK),)


def test_dependency_error_short_circuits_resolver() -> None:
    calls = 0

    def resolver(values):
        nonlocal calls
        calls += 1
        return values['general.a']

    spec = OverKpiSpec(
        key='general.total',
        area=KpiArea.GENERAL,
        dependencies=('general.a',),
        resolver=resolver,
        value_type=KpiValueType.FLOAT,
    )
    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={'general.a': _evaluation('general.a', status=KpiStatus.ERROR)},
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )
    assert evaluation.status is KpiStatus.ERROR
    assert evaluation.value_type is KpiValueType.FLOAT
    assert evaluation.error == 'KpiDependencyError'
    assert calls == 0


def test_missing_dependency_value_is_available_to_resolver_as_none() -> None:
    spec = OverKpiSpec(
        key='general.fallback',
        area=KpiArea.GENERAL,
        dependencies=('general.a',),
        resolver=lambda values: 0 if values['general.a'] is None else values['general.a'],
        value_type=KpiValueType.INTEGER,
    )
    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={'general.a': _evaluation('general.a', status=KpiStatus.MISSING)},
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )
    assert evaluation.status is KpiStatus.OK
    assert evaluation.value == '0'


def test_json_over_requires_json_container() -> None:
    spec = OverKpiSpec(
        key='general.payload',
        area=KpiArea.GENERAL,
        dependencies=('general.a',),
        resolver=lambda values: 1,
        value_kind=KpiValueKind.JSON,
    )
    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={'general.a': _evaluation('general.a')},
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )
    assert evaluation.status is KpiStatus.ERROR
    assert evaluation.error == 'TypeError'
