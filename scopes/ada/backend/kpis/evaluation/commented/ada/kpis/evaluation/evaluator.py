# Evaluación pura de KPI base y Over KPI. Over consume resultados ya calculados y no vuelve a leer Operational Data.
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from ada.kpis.core import (
    KpiEvaluation,
    KpiMode,
    KpiResult,
    KpiSourceTrace,
    KpiSpec,
    KpiStatus,
    KpiValueKind,
    KpiWatermark,
    OverKpiSpec,
    normalize_kpi_value,
)
from ada.kpis.evaluation.dependencies import KpiDependencies
from ada.kpis.evaluation.errors import (
    KpiDependencyError,
    KpiEvaluationContractError,
)
from ada.kpis.evaluation.values import missing_value, numeric_value
from atlanticus.operational_data.core import DataRuntimeContext, DataSource


def evaluate_kpi(
    *,
    spec: KpiSpec,
    context: DataRuntimeContext,
    watermark: KpiWatermark,
    source_watermarks: Mapping[DataSource, KpiWatermark | None] | None = None,
    evaluated_at_utc: datetime | None = None,
) -> KpiEvaluation:
    if not isinstance(spec, KpiSpec):
        raise TypeError('spec must be KpiSpec')
    if not isinstance(context, DataRuntimeContext):
        raise TypeError('context must be DataRuntimeContext')
    if not isinstance(watermark, KpiWatermark):
        raise TypeError('watermark must be KpiWatermark')
    traces = _source_traces(spec, source_watermarks or {})
    evaluated_at = datetime.now(UTC) if evaluated_at_utc is None else evaluated_at_utc
    try:
        value = _resolve_value(spec, context)
        result = _result(spec, value)
    except Exception as error:
        result = KpiResult(
            status=KpiStatus.ERROR,
            value_kind=_expected_kind(spec),
            error=type(error).__name__,
        )
    return KpiEvaluation(
        key=spec.key,
        area=spec.area.value,
        watermark=watermark,
        evaluated_at_utc=evaluated_at,
        result=result,
        persist_history=spec.persist_history,
        sources=traces,
    )


def evaluate_over_kpi(
    *,
    spec: OverKpiSpec,
    dependencies: Mapping[str, KpiEvaluation],
    watermark: KpiWatermark,
    evaluated_at_utc: datetime | None = None,
) -> KpiEvaluation:
    if not isinstance(spec, OverKpiSpec):
        raise TypeError('spec must be OverKpiSpec')
    if not isinstance(watermark, KpiWatermark):
        raise TypeError('watermark must be KpiWatermark')
    resolved = _over_dependencies(
        spec=spec,
        dependencies=dependencies,
        watermark=watermark,
    )
    evaluated_at = datetime.now(UTC) if evaluated_at_utc is None else evaluated_at_utc
    traces = _dependency_source_traces(resolved)
    if any(evaluation.status is KpiStatus.ERROR for evaluation in resolved.values()):
        result = KpiResult(
            status=KpiStatus.ERROR,
            value_kind=spec.value_kind,
            error=KpiDependencyError.__name__,
        )
    else:
        values = KpiDependencies({key: resolved[key].value for key in spec.dependencies})
        try:
            value = spec.resolver(values)
            result = _over_result(spec, value)
        except Exception as error:
            result = KpiResult(
                status=KpiStatus.ERROR,
                value_kind=spec.value_kind,
                error=type(error).__name__,
            )
    return KpiEvaluation(
        key=spec.key,
        area=spec.area.value,
        watermark=watermark,
        evaluated_at_utc=evaluated_at,
        result=result,
        persist_history=spec.persist_history,
        sources=traces,
    )


def _source_traces(
    spec: KpiSpec,
    watermarks: Mapping[DataSource, KpiWatermark | None],
) -> tuple[KpiSourceTrace, ...]:
    sources = tuple(dict.fromkeys(requirement.source for requirement in spec.requirements))
    return tuple(KpiSourceTrace(source, watermarks.get(source)) for source in sources)


def _resolve_value(spec: KpiSpec, context: DataRuntimeContext) -> object:
    if spec.mode is KpiMode.CUSTOM:
        if spec.custom_resolver is None:
            raise RuntimeError('custom KPI resolver is missing')
        return spec.custom_resolver(context)
    requirement = spec.requirements[0]
    frame = context.get(requirement.source, requirement.partition)
    if spec.mode in {KpiMode.LATEST, KpiMode.STATUS}:
        return frame.last_value(spec.columns[0].name)
    if spec.mode is KpiMode.LATEST_NUMBER:
        return frame.last_value_number(spec.columns[0].name)
    values = []
    for column in spec.columns:
        if column.name not in frame.dataframe.columns:
            raise KeyError(column.name)
        for value in frame.dataframe[column.name].tolist():
            normalized = numeric_value(value)
            if normalized is not None:
                values.append(normalized)
    if not values:
        return None
    if spec.mode is KpiMode.SUM:
        return sum(values)
    if spec.mode is KpiMode.MAX:
        return max(values)
    raise RuntimeError(f'unsupported KPI mode: {spec.mode.value}')


def _result(spec: KpiSpec, value: object) -> KpiResult:
    if missing_value(value):
        return KpiResult(KpiStatus.MISSING, _expected_kind(spec))
    normalized = normalize_kpi_value(value)
    if spec.mode in {KpiMode.LATEST_NUMBER, KpiMode.SUM, KpiMode.MAX}:
        numeric = numeric_value(normalized)
        if numeric is None:
            return KpiResult(KpiStatus.MISSING, KpiValueKind.VALUE)
        if spec.decimals is not None:
            numeric = round(numeric, spec.decimals)
        normalized = numeric
    return KpiResult(
        status=KpiStatus.OK,
        value_kind=_value_kind(normalized),
        value=normalized,
        parsed_value=normalized,
    )


def _over_result(spec: OverKpiSpec, value: object) -> KpiResult:
    if missing_value(value):
        return KpiResult(KpiStatus.MISSING, spec.value_kind)
    normalized = normalize_kpi_value(value)
    if spec.value_kind is KpiValueKind.JSON:
        if not isinstance(normalized, list | dict):
            raise TypeError('JSON Over KPI resolver must return a JSON container')
    else:
        if isinstance(normalized, list | dict):
            raise TypeError('VALUE Over KPI resolver must return a scalar value')
        if spec.decimals is not None:
            numeric = numeric_value(normalized)
            if numeric is None:
                raise TypeError('Over KPI decimals require a numeric value')
            normalized = round(numeric, spec.decimals)
    return KpiResult(
        status=KpiStatus.OK,
        value_kind=spec.value_kind,
        value=normalized,
        parsed_value=normalized,
    )


def _over_dependencies(
    *,
    spec: OverKpiSpec,
    dependencies: Mapping[str, KpiEvaluation],
    watermark: KpiWatermark,
) -> dict[str, KpiEvaluation]:
    if not isinstance(dependencies, Mapping):
        raise TypeError('dependencies must be a mapping')
    if set(dependencies) != set(spec.dependencies):
        raise KpiEvaluationContractError(
            'Over KPI dependency evaluations must match declared dependencies'
        )
    resolved: dict[str, KpiEvaluation] = {}
    for key in spec.dependencies:
        evaluation = dependencies[key]
        if not isinstance(evaluation, KpiEvaluation):
            raise TypeError('Over KPI dependencies must contain KpiEvaluation values')
        if evaluation.key != key:
            raise KpiEvaluationContractError(
                'Over KPI dependency evaluation key does not match its mapping key'
            )
        if evaluation.watermark != watermark:
            raise KpiEvaluationContractError(
                'Over KPI dependencies must use the current KPI watermark'
            )
        resolved[key] = evaluation
    return resolved


def _dependency_source_traces(
    dependencies: Mapping[str, KpiEvaluation],
) -> tuple[KpiSourceTrace, ...]:
    traces: dict[DataSource, KpiSourceTrace] = {}
    for evaluation in dependencies.values():
        for trace in evaluation.sources:
            existing = traces.get(trace.source)
            if existing is not None and existing.watermark != trace.watermark:
                raise KpiEvaluationContractError(
                    'Over KPI dependency source watermarks are inconsistent'
                )
            traces.setdefault(trace.source, trace)
    return tuple(traces.values())


def _value_kind(value: object) -> KpiValueKind:
    return KpiValueKind.JSON if isinstance(value, list | dict) else KpiValueKind.VALUE


def _expected_kind(spec: KpiSpec) -> KpiValueKind:
    return KpiValueKind.JSON if spec.mode is KpiMode.CUSTOM else KpiValueKind.VALUE
