# Espejo pedagógico: explica la evaluación KPI pura, sin incorporar loading ni clientes de infraestructura.
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
    normalize_kpi_value,
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
        area=spec.area,
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


def _value_kind(value: object) -> KpiValueKind:
    return KpiValueKind.JSON if isinstance(value, list | dict) else KpiValueKind.VALUE


def _expected_kind(spec: KpiSpec) -> KpiValueKind:
    return KpiValueKind.JSON if spec.mode is KpiMode.CUSTOM else KpiValueKind.VALUE
