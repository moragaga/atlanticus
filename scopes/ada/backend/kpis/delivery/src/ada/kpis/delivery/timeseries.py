from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from ada.kpis.delivery.configuration import KpiDeliveryConfiguration
from ada.kpis.delivery.errors import KpiDeliveryValidationError
from ada.kpis.delivery.models import (
    KpiTimeseriesManifest,
    KpiTimeseriesSeries,
    KpiTimeseriesSnapshot,
)
from ada.kpis.delivery.revision import (
    canonical_revision,
    require_aware_datetime,
    utc_iso,
)

TIMESERIES_STEP_SECONDS = 120


def align_timeseries_end(value: datetime) -> datetime:
    normalized = require_aware_datetime(value, field_name='end_utc')
    epoch_seconds = int(normalized.timestamp())
    aligned_seconds = epoch_seconds - (epoch_seconds % TIMESERIES_STEP_SECONDS)
    return datetime.fromtimestamp(aligned_seconds, tz=UTC)


def _normalize_history(
    history: Mapping[datetime, Any],
    *,
    key: str,
) -> dict[datetime, Any]:
    if not isinstance(history, Mapping):
        raise TypeError(f'history for {key} must be a mapping')
    normalized: dict[datetime, Any] = {}
    for timestamp, value in history.items():
        point_at = require_aware_datetime(timestamp, field_name=f'history timestamp for {key}')
        canonical_revision({'value': value})
        normalized[point_at] = value
    return normalized


def project_kpi_timeseries(
    *,
    configuration: KpiDeliveryConfiguration,
    histories: Mapping[str, Mapping[datetime, Any]],
    historian_revision: str,
    end_utc: datetime,
    published_at_utc: datetime,
) -> KpiTimeseriesSnapshot:
    if not isinstance(configuration, KpiDeliveryConfiguration):
        raise TypeError('configuration must be KpiDeliveryConfiguration')
    if not isinstance(histories, Mapping):
        raise TypeError('histories must be a mapping')
    if not isinstance(historian_revision, str):
        raise TypeError('historian_revision must be str')
    if not historian_revision or historian_revision != historian_revision.strip():
        raise KpiDeliveryValidationError('historian_revision must be a non-empty trimmed string')

    aligned_end = align_timeseries_end(end_utc)
    end_text = utc_iso(aligned_end, field_name='end_utc')
    published_at = utc_iso(published_at_utc, field_name='published_at_utc')
    series: dict[str, KpiTimeseriesSeries] = {}
    destinations: dict[str, list[str]] = {}

    for binding in configuration.bindings:
        if not binding.series_enabled:
            continue
        hours = binding.series_hours
        if hours is None:
            raise KpiDeliveryValidationError('series_hours is required for enabled series')
        start = aligned_end - timedelta(hours=hours)
        point_count = hours * 3600 // TIMESERIES_STEP_SECONDS
        normalized_history = _normalize_history(histories.get(binding.key, {}), key=binding.key)
        values = tuple(
            normalized_history.get(start + timedelta(seconds=TIMESERIES_STEP_SECONDS * index))
            for index in range(1, point_count + 1)
        )
        series[binding.key] = KpiTimeseriesSeries(
            hours=hours,
            start_utc=utc_iso(start, field_name='start_utc'),
            end_utc=end_text,
            values=values,
        )
        for destination_key in binding.destination_keys:
            destinations.setdefault(destination_key, []).append(binding.key)

    frozen_destinations = {destination: tuple(keys) for destination, keys in destinations.items()}
    revision_payload = {
        'schema_version': 1,
        'configuration_revision': configuration.revision,
        'tool_projection_revision': configuration.tool_projection_revision,
        'historian_revision': historian_revision,
        'end_utc': end_text,
        'step_seconds': TIMESERIES_STEP_SECONDS,
        'destinations': {
            destination: list(keys) for destination, keys in frozen_destinations.items()
        },
        'series': {key: value.to_payload() for key, value in series.items()},
    }
    manifest = KpiTimeseriesManifest(
        schema_version=1,
        revision=canonical_revision(revision_payload),
        configuration_revision=configuration.revision,
        tool_projection_revision=configuration.tool_projection_revision,
        historian_revision=historian_revision,
        published_at_utc=published_at,
    )
    return KpiTimeseriesSnapshot(
        manifest=manifest,
        end_utc=end_text,
        step_seconds=TIMESERIES_STEP_SECONDS,
        destinations=frozen_destinations,
        series=series,
    )
