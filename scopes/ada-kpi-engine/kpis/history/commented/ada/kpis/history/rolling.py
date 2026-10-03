# Contrato compartido del read model rolling de Timeseries producido por KPI Historian.
# Define identidad, horizonte, grilla y metadata, pero no conoce filesystem ni runtime de proceso.
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Self

from ada.kpis.history.errors import KpiHistoryContractError
from ada.kpis.history.revision import historian_revision, historian_watermark_text

ROLLING_SCHEMA_VERSION = 1
ROLLING_GRID_SECONDS = 30
ROLLING_MAX_HOURS = 24
ROLLING_DIRECTORY = 'timeseries'
ROLLING_FILENAME = 'current.parquet'
ROLLING_METADATA_KEY = 'ada_kpi_timeseries'
ROLLING_TIMESTAMP_COLUMN = 'timestamp_utc'
ROLLING_VALUE_TYPES = frozenset({'text', 'integer', 'float', 'boolean'})


@dataclass(frozen=True, slots=True)
class KpiRollingMetadata:
    watermark_utc: datetime
    historian_revision: str
    coverage_start_utc: datetime | None
    coverage_end_utc: datetime | None
    value_types: Mapping[str, str]

    def __post_init__(self) -> None:
        # La metadata siempre representa una vista coherente con una revisión durable del Historian.
        watermark = _aligned_datetime(self.watermark_utc, 'watermark_utc')
        expected_revision = historian_revision(watermark_utc=watermark)
        if self.historian_revision != expected_revision:
            raise KpiHistoryContractError('KPI rolling historian_revision is invalid')
        start = (
            None
            if self.coverage_start_utc is None
            else _aligned_datetime(self.coverage_start_utc, 'coverage_start_utc')
        )
        end = (
            None
            if self.coverage_end_utc is None
            else _aligned_datetime(self.coverage_end_utc, 'coverage_end_utc')
        )
        if (start is None) != (end is None):
            raise KpiHistoryContractError(
                'KPI rolling coverage_start_utc and coverage_end_utc must both be set '
                'or both be null'
            )
        if start is not None and end is not None:
            if start > end:
                raise KpiHistoryContractError(
                    'KPI rolling coverage_start_utc must not exceed coverage_end_utc'
                )
            if end > watermark:
                raise KpiHistoryContractError(
                    'KPI rolling coverage_end_utc must not exceed watermark_utc'
                )
            if start <= watermark - timedelta(hours=ROLLING_MAX_HOURS):
                raise KpiHistoryContractError(
                    'KPI rolling coverage_start_utc must be inside the rolling horizon'
                )
        normalized_types = _value_types(self.value_types)
        if start is None and normalized_types:
            raise KpiHistoryContractError(
                'KPI rolling value_types must be empty when physical coverage is empty'
            )
        if start is not None and not normalized_types:
            raise KpiHistoryContractError(
                'KPI rolling value_types must not be empty when physical coverage exists'
            )
        object.__setattr__(self, 'watermark_utc', watermark)
        object.__setattr__(self, 'coverage_start_utc', start)
        object.__setattr__(self, 'coverage_end_utc', end)
        object.__setattr__(self, 'value_types', MappingProxyType(normalized_types))

    def to_payload(self) -> dict[str, Any]:
        return {
            'schema_version': ROLLING_SCHEMA_VERSION,
            'watermark_utc': historian_watermark_text(self.watermark_utc),
            'historian_revision': self.historian_revision,
            'grid_seconds': ROLLING_GRID_SECONDS,
            'max_hours': ROLLING_MAX_HOURS,
            'coverage_start_utc': _optional_watermark_text(self.coverage_start_utc),
            'coverage_end_utc': _optional_watermark_text(self.coverage_end_utc),
            'value_types': dict(self.value_types),
        }

    def to_bytes(self) -> bytes:
        # JSON canónico evita metadata dependiente del orden de diccionarios.
        return json.dumps(
            self.to_payload(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Self:
        if not isinstance(payload, Mapping):
            raise TypeError('KPI rolling metadata payload must be a mapping')
        expected = {
            'schema_version',
            'watermark_utc',
            'historian_revision',
            'grid_seconds',
            'max_hours',
            'coverage_start_utc',
            'coverage_end_utc',
            'value_types',
        }
        if set(payload) != expected:
            raise KpiHistoryContractError(
                'KPI rolling metadata payload contains unexpected or missing fields'
            )
        if payload['schema_version'] != ROLLING_SCHEMA_VERSION:
            raise KpiHistoryContractError('unsupported KPI rolling metadata schema version')
        if payload['grid_seconds'] != ROLLING_GRID_SECONDS:
            raise KpiHistoryContractError('unsupported KPI rolling grid_seconds')
        if payload['max_hours'] != ROLLING_MAX_HOURS:
            raise KpiHistoryContractError('unsupported KPI rolling max_hours')
        watermark = _datetime_from_text(payload['watermark_utc'], 'watermark_utc')
        start = _optional_datetime_from_text(payload['coverage_start_utc'], 'coverage_start_utc')
        end = _optional_datetime_from_text(payload['coverage_end_utc'], 'coverage_end_utc')
        revision = payload['historian_revision']
        if not isinstance(revision, str) or not revision or revision != revision.strip():
            raise KpiHistoryContractError('KPI rolling historian_revision is invalid')
        value_types = payload['value_types']
        if not isinstance(value_types, Mapping):
            raise KpiHistoryContractError('KPI rolling value_types is invalid')
        return cls(
            watermark_utc=watermark,
            historian_revision=revision,
            coverage_start_utc=start,
            coverage_end_utc=end,
            value_types=value_types,
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        if not isinstance(value, bytes):
            raise TypeError('KPI rolling metadata must be bytes')
        try:
            payload = json.loads(value.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KpiHistoryContractError('KPI rolling metadata is invalid JSON') from error
        return cls.from_payload(payload)


def _aligned_datetime(value: datetime, field_name: str) -> datetime:
    text = historian_watermark_text(value)
    normalized = _datetime_from_text(text, field_name)
    if int(normalized.timestamp()) % ROLLING_GRID_SECONDS != 0:
        raise KpiHistoryContractError(
            f'KPI rolling {field_name} must align to the {ROLLING_GRID_SECONDS}-second grid'
        )
    return normalized


def _datetime_from_text(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise KpiHistoryContractError(f'KPI rolling {field_name} is invalid')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise KpiHistoryContractError(f'KPI rolling {field_name} is invalid') from error


def _optional_datetime_from_text(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _datetime_from_text(value, field_name)


def _optional_watermark_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return historian_watermark_text(value)


def _value_types(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError('KPI rolling value_types must be a mapping')
    normalized: dict[str, str] = {}
    for key, value_type in value.items():
        if not isinstance(key, str) or not key or key != key.strip():
            raise KpiHistoryContractError('KPI rolling value_types key is invalid')
        if value_type not in ROLLING_VALUE_TYPES:
            raise KpiHistoryContractError('KPI rolling value_type is invalid')
        normalized[key] = value_type
    return dict(sorted(normalized.items()))
