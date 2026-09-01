from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class KpiDeliveryStatus(StrEnum):
    OK = 'ok'
    MISSING = 'missing'
    ERROR = 'error'


@dataclass(frozen=True, slots=True)
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
        if self.status is KpiDeliveryStatus.OK:
            if self.value_kind is None:
                raise ValueError('value_kind is required for ok delivery values')
            if self.value is None:
                raise ValueError('value is required for ok delivery values')
        elif self.status is KpiDeliveryStatus.MISSING:
            if self.value_kind is not None or self.value is not None:
                raise ValueError('missing delivery values must not carry value_kind or value')
        elif self.value is not None:
            raise ValueError('error delivery values must not carry a value')

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
class KpiTimeseriesSeries:
    hours: int
    start_utc: str
    end_utc: str
    values: tuple[Any, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            'hours': self.hours,
            'start_utc': self.start_utc,
            'end_utc': self.end_utc,
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
