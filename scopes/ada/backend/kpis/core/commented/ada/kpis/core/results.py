# Contratos de resultado KPI; VALUE transporta textos tipados y JSON conserva una única representación estructurada.
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

from ada.kpis.core.enums import KpiStatus, KpiValueKind, KpiValueType
from ada.kpis.core.values import KpiNativeValue, normalize_kpi_value
from ada.kpis.core.watermark import KpiWatermark
from atlanticus.operational_data.core import DataSource


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f'{field} must be a datetime')
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{field} must be timezone-aware')
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class KpiResult:
    status: KpiStatus
    value_kind: KpiValueKind
    value: KpiNativeValue = None
    parsed_value: KpiNativeValue = None
    error: str | None = None
    value_type: KpiValueType | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, KpiStatus):
            raise TypeError('KPI result status must be KpiStatus')
        if not isinstance(self.value_kind, KpiValueKind):
            raise TypeError('KPI result value_kind must be KpiValueKind')
        if self.value_type is not None and not isinstance(self.value_type, KpiValueType):
            raise TypeError('KPI result value_type must be KpiValueType or None')
        if self.value_kind is KpiValueKind.VALUE:
            if self.value_type is None:
                raise ValueError('VALUE KPI result requires value_type')
            value = self.value
            parsed = self.parsed_value
            if value is not None and not isinstance(value, str):
                raise TypeError('VALUE KPI result value must be str or None')
            if parsed is not None and not isinstance(parsed, str):
                raise TypeError('VALUE KPI result parsed_value must be str or None')
        else:
            if self.value_type is not None:
                raise ValueError('JSON KPI result must not declare value_type')
            value = normalize_kpi_value(self.value)
            parsed = normalize_kpi_value(self.parsed_value)
            if parsed is not None:
                raise ValueError('JSON KPI result must not expose parsed_value')
            if value is not None and not isinstance(value, list | dict):
                raise TypeError('JSON KPI result value must be a list, dict or None')
        if self.status is KpiStatus.ERROR:
            if value is not None or parsed is not None:
                raise ValueError('error KPI result must not expose value or parsed_value')
            if not isinstance(self.error, str) or not self.error:
                raise ValueError('error KPI result requires a sanitized error type')
        elif self.status is KpiStatus.MISSING:
            if value is not None or parsed is not None or self.error is not None:
                raise ValueError('missing KPI result must contain only null value fields')
        else:
            if value is None or self.error is not None:
                raise ValueError('ok KPI result requires a value and no error')
            if self.value_kind is KpiValueKind.VALUE and parsed is None:
                raise ValueError('ok VALUE KPI result requires parsed_value')
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'parsed_value', parsed)

    def to_payload(self) -> dict[str, Any]:
        return {
            'status': self.status.value,
            'value_kind': self.value_kind.value,
            'value_type': None if self.value_type is None else self.value_type.value,
            'value': self.value,
            'parsed_value': self.parsed_value,
            'error': self.error,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        if not isinstance(payload, dict):
            raise TypeError('KPI result payload must be a dict')
        expected = {'status', 'value_kind', 'value_type', 'value', 'parsed_value', 'error'}
        if set(payload) != expected:
            raise ValueError('KPI result payload contains unexpected or missing fields')
        value_type = payload['value_type']
        return cls(
            status=KpiStatus(payload['status']),
            value_kind=KpiValueKind(payload['value_kind']),
            value_type=None if value_type is None else KpiValueType(value_type),
            value=payload['value'],
            parsed_value=payload['parsed_value'],
            error=payload['error'],
        )


@dataclass(frozen=True, slots=True)
class KpiSourceTrace:
    source: DataSource
    watermark: KpiWatermark | None

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataSource):
            raise TypeError('KPI source trace source must be DataSource')
        if self.watermark is not None and not isinstance(self.watermark, KpiWatermark):
            raise TypeError('KPI source trace watermark must be KpiWatermark')

    def to_payload(self) -> dict[str, Any]:
        return {
            'source': self.source.value,
            'watermark_utc': None if self.watermark is None else self.watermark.to_text(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        if not isinstance(payload, dict) or set(payload) != {'source', 'watermark_utc'}:
            raise ValueError('KPI source trace payload is invalid')
        watermark = payload['watermark_utc']
        return cls(
            source=DataSource(payload['source']),
            watermark=None if watermark is None else KpiWatermark.from_text(watermark),
        )


@dataclass(frozen=True, slots=True)
class KpiEvaluation:
    key: str
    area: str
    watermark: KpiWatermark
    evaluated_at_utc: datetime
    result: KpiResult
    persist_history: bool = True
    sources: tuple[KpiSourceTrace, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError('KPI evaluation key must be non-empty')
        if not isinstance(self.area, str) or not self.area:
            raise ValueError('KPI evaluation area must be non-empty')
        if not isinstance(self.watermark, KpiWatermark):
            raise TypeError('KPI evaluation watermark must be KpiWatermark')
        if not isinstance(self.result, KpiResult):
            raise TypeError('KPI evaluation result must be KpiResult')
        if not isinstance(self.persist_history, bool):
            raise TypeError('KPI evaluation persist_history must be bool')
        sources = tuple(self.sources)
        if not all(isinstance(source, KpiSourceTrace) for source in sources):
            raise TypeError('evaluation sources must contain KpiSourceTrace values')
        if len({source.source for source in sources}) != len(sources):
            raise ValueError('evaluation source traces must be unique by source')
        object.__setattr__(
            self, 'evaluated_at_utc', _utc(self.evaluated_at_utc, 'evaluated_at_utc')
        )
        object.__setattr__(self, 'sources', sources)

    @property
    def status(self) -> KpiStatus:
        return self.result.status

    @property
    def value_kind(self) -> KpiValueKind:
        return self.result.value_kind

    @property
    def value_type(self) -> KpiValueType | None:
        return self.result.value_type

    @property
    def value(self) -> KpiNativeValue:
        return self.result.value

    @property
    def parsed_value(self) -> KpiNativeValue:
        return self.result.parsed_value

    @property
    def error(self) -> str | None:
        return self.result.error

    def to_payload(self) -> dict[str, Any]:
        return {
            'key': self.key,
            'area': self.area,
            'watermark_utc': self.watermark.to_text(),
            'evaluated_at_utc': self.evaluated_at_utc.isoformat(timespec='microseconds').replace(
                '+00:00', 'Z'
            ),
            'result': self.result.to_payload(),
            'persist_history': self.persist_history,
            'sources': [source.to_payload() for source in self.sources],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        if not isinstance(payload, dict):
            raise TypeError('KPI evaluation payload must be a dict')
        expected = {
            'key',
            'area',
            'watermark_utc',
            'evaluated_at_utc',
            'result',
            'persist_history',
            'sources',
        }
        if set(payload) != expected:
            raise ValueError('KPI evaluation payload contains unexpected or missing fields')
        try:
            evaluated_at = datetime.fromisoformat(
                payload['evaluated_at_utc'].replace('Z', '+00:00')
            )
        except (AttributeError, ValueError) as error:
            raise ValueError('KPI evaluated_at_utc is invalid') from error
        sources = payload['sources']
        if not isinstance(sources, list):
            raise TypeError('KPI evaluation sources must be a list')
        return cls(
            key=payload['key'],
            area=payload['area'],
            watermark=KpiWatermark.from_text(payload['watermark_utc']),
            evaluated_at_utc=evaluated_at,
            result=KpiResult.from_payload(payload['result']),
            persist_history=payload['persist_history'],
            sources=tuple(KpiSourceTrace.from_payload(source) for source in sources),
        )
