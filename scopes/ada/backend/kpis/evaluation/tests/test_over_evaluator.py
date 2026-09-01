from datetime import UTC, datetime

import pytest

from ada.kpis.core import (
    KpiArea,
    KpiEvaluation,
    KpiResult,
    KpiSourceTrace,
    KpiStatus,
    KpiValueKind,
    KpiWatermark,
    OverKpiSpec,
)
from ada.kpis.evaluation import (
    KpiDependencies,
    KpiDependencyNotRequestedError,
    evaluate_over_kpi,
)
from atlanticus.operational_data.core import DataSource

WATERMARK = KpiWatermark(datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
EVALUATED_AT = datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC)


def _evaluation(
    key: str,
    *,
    status: KpiStatus = KpiStatus.OK,
    value=10.0,
    source: DataSource = DataSource.PI_INTERPOLATED,
) -> KpiEvaluation:
    if status is KpiStatus.ERROR:
        result = KpiResult(KpiStatus.ERROR, KpiValueKind.VALUE, error='RuntimeError')
    elif status is KpiStatus.MISSING:
        result = KpiResult(KpiStatus.MISSING, KpiValueKind.VALUE)
    else:
        result = KpiResult(
            KpiStatus.OK,
            KpiValueKind.VALUE,
            value=value,
            parsed_value=value,
        )
    return KpiEvaluation(
        key=key,
        area='general',
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
        result=result,
        sources=(KpiSourceTrace(source, WATERMARK),),
    )


def test_dependencies_reject_access_to_undeclared_key():
    values = KpiDependencies({'general.a': 1})

    with pytest.raises(KpiDependencyNotRequestedError):
        _ = values['general.b']


def test_over_evaluation_consumes_declared_values_and_rounds_numeric_result():
    spec = OverKpiSpec(
        key='general.ratio',
        area=KpiArea.GENERAL,
        dependencies=('general.a', 'general.b'),
        resolver=lambda values: values['general.a'] / values['general.b'],
        decimals=2,
        persist_history=True,
    )

    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={
            'general.a': _evaluation('general.a', value=10.0),
            'general.b': _evaluation('general.b', value=3.0),
        },
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )

    assert evaluation.status is KpiStatus.OK
    assert evaluation.value == 3.33
    assert evaluation.persist_history is True
    assert evaluation.sources == (KpiSourceTrace(DataSource.PI_INTERPOLATED, WATERMARK),)


def test_dependency_error_short_circuits_resolver():
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
    )

    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={'general.a': _evaluation('general.a', status=KpiStatus.ERROR)},
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )

    assert evaluation.status is KpiStatus.ERROR
    assert evaluation.error == 'KpiDependencyError'
    assert calls == 0


def test_missing_dependency_value_is_available_to_resolver_as_none():
    spec = OverKpiSpec(
        key='general.fallback',
        area=KpiArea.GENERAL,
        dependencies=('general.a',),
        resolver=lambda values: 0 if values['general.a'] is None else values['general.a'],
    )

    evaluation = evaluate_over_kpi(
        spec=spec,
        dependencies={'general.a': _evaluation('general.a', status=KpiStatus.MISSING)},
        watermark=WATERMARK,
        evaluated_at_utc=EVALUATED_AT,
    )

    assert evaluation.status is KpiStatus.OK
    assert evaluation.value == 0


def test_json_over_requires_json_container():
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
