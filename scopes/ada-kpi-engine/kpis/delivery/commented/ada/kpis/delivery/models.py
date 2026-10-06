# Modelos de Delivery; Timeseries conserva value_type una vez por serie y puntos ya reconstruidos.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

_VALUE_TYPES = frozenset({'text', 'integer', 'float', 'boolean'})
_VALUE_KINDS = frozenset({'value', 'json'})


class KpiDeliveryStatus(StrEnum):
    OK = 'ok'
    MISSING = 'missing'
    ERROR = 'error'


@dataclass(frozen=True, slots=True)
# Latest conserva el tipo contractual, pero los estados degradados nunca transportan valor.
class KpiLatestValue:
    status: KpiDeliveryStatus
    value_kind: str | None
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.status, KpiDeliveryStatus):
            raise TypeError('status must be KpiDeliveryStatus')
        if self.value_kind is not None:
            if not isinstance(self.value_kind, str):
                raise TypeError('value_kind must be str or None')
            if not self.value_kind or self.value_kind != self.value_kind.strip():
                raise ValueError('value_kind must be a non-empty trimmed string')
            if self.value_kind not in _VALUE_KINDS:
                raise ValueError('value_kind must be value or json')
        if self.status is KpiDeliveryStatus.OK:
            if self.value_kind is None:
                raise ValueError('value_kind is required for ok delivery values')
            if self.value is None:
                raise ValueError('value is required for ok delivery values')
            if self.value_kind == 'json' and not isinstance(self.value, list | dict):
                raise TypeError('json delivery values must contain a list or dict')
        elif self.value is not None:
            raise ValueError(f'{self.status.value} delivery values must not carry a value')

    @classmethod
    def missing(cls) -> KpiLatestValue:
        return cls(status=KpiDeliveryStatus.MISSING, value_kind=None, value=None)

    def to_payload(self) -> dict[str, Any]:
        return {
            'status': self.status.value,
            'value_kind': self.value_kind,
            'value': self.value,
        }


@dataclass(frozen=True, slots=True)
class KpiLatestManifest:
    schema_version: int
    revision: str
    configuration_revision: str
    tool_projection_revision: str | None
    watermark_utc: str
    published_at_utc: str

    def to_payload(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'revision': self.revision,
            'configuration_revision': self.configuration_revision,
            'tool_projection_revision': self.tool_projection_revision,
            'watermark_utc': self.watermark_utc,
            'published_at_utc': self.published_at_utc,
        }


@dataclass(frozen=True, slots=True)
class KpiLatestSnapshot:
    manifest: KpiLatestManifest
    destinations: dict[str, dict[str, KpiLatestValue]]

    def to_payload(self) -> dict[str, Any]:
        return {
            'id': 'latest',
            'partition_id': 'kpis',
            'document_type': 'ada_kpi_latest_delivery',
            'manifest': self.manifest.to_payload(),
            'destinations': {
                destination: {key: value.to_payload() for key, value in values.items()}
                for destination, values in self.destinations.items()
            },
        }


@dataclass(frozen=True, slots=True)
class KpiTimeseriesHistory:
    value_type: str
    values: Mapping[datetime, str]

    def __post_init__(self) -> None:
        if not isinstance(self.value_type, str) or self.value_type not in _VALUE_TYPES:
            raise ValueError('timeseries history value_type is invalid')
        if not isinstance(self.values, Mapping):
            raise TypeError('timeseries history values must be a mapping')
        normalized: dict[datetime, str] = {}
        for timestamp, value in self.values.items():
            if not isinstance(timestamp, datetime):
                raise TypeError('timeseries history timestamps must be datetime values')
            if not isinstance(value, str):
                raise TypeError('timeseries history values must contain canonical strings')
            normalized[timestamp] = value
        object.__setattr__(self, 'values', MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class KpiTimeseriesSeries:
    hours: int
    start_utc: str
    end_utc: str
    value_type: str | None
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if self.value_type is not None and self.value_type not in _VALUE_TYPES:
            raise ValueError('timeseries series value_type is invalid')
        if self.value_type is None and any(value is not None for value in self.values):
            raise ValueError('timeseries series with values requires value_type')

    def to_payload(self) -> dict[str, Any]:
        return {
            'hours': self.hours,
            'start_utc': self.start_utc,
            'end_utc': self.end_utc,
            'value_type': self.value_type,
            'values': list(self.values),
        }


@dataclass(frozen=True, slots=True)
class KpiTimeseriesManifest:
    schema_version: int
    revision: str
    configuration_revision: str
    tool_projection_revision: str | None
    historian_revision: str
    published_at_utc: str

    def to_payload(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'revision': self.revision,
            'configuration_revision': self.configuration_revision,
            'tool_projection_revision': self.tool_projection_revision,
            'historian_revision': self.historian_revision,
            'published_at_utc': self.published_at_utc,
        }


@dataclass(frozen=True, slots=True)
class KpiTimeseriesSnapshot:
    manifest: KpiTimeseriesManifest
    end_utc: str
    step_seconds: int
    destinations: dict[str, tuple[str, ...]]
    series: dict[str, KpiTimeseriesSeries]

    def to_payload(self) -> dict[str, Any]:
        return {
            'id': 'timeseries',
            'partition_id': 'kpis',
            'document_type': 'ada_kpi_timeseries_delivery',
            'manifest': self.manifest.to_payload(),
            'end_utc': self.end_utc,
            'step_seconds': self.step_seconds,
            'destinations': {
                destination: list(keys) for destination, keys in self.destinations.items()
            },
            'series': {key: value.to_payload() for key, value in self.series.items()},
        }
