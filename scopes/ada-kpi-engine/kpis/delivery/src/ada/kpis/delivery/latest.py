from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ada.kpis.delivery.configuration import KpiDeliveryConfiguration
from ada.kpis.delivery.models import (
    KpiDeliveryStatus,
    KpiLatestManifest,
    KpiLatestSnapshot,
    KpiLatestValue,
)
from ada.kpis.delivery.revision import canonical_revision, utc_iso


def _normalized_latest_value(value: KpiLatestValue) -> KpiLatestValue:
    if not isinstance(value, KpiLatestValue):
        raise TypeError('latest values must contain KpiLatestValue values')
    if value.status is KpiDeliveryStatus.ERROR:
        return KpiLatestValue(
            status=KpiDeliveryStatus.ERROR,
            value_kind=value.value_kind,
            value=None,
        )
    if value.status is KpiDeliveryStatus.MISSING:
        return KpiLatestValue.missing()
    canonical_revision({'value': value.value})
    return value


def project_kpi_latest(
    *,
    configuration: KpiDeliveryConfiguration,
    values: Mapping[str, KpiLatestValue],
    watermark_utc: datetime,
    published_at_utc: datetime,
) -> KpiLatestSnapshot:
    if not isinstance(configuration, KpiDeliveryConfiguration):
        raise TypeError('configuration must be KpiDeliveryConfiguration')
    if not isinstance(values, Mapping):
        raise TypeError('values must be a mapping')

    destinations: dict[str, dict[str, KpiLatestValue]] = {}
    for binding in configuration.bindings:
        if not binding.latest_enabled:
            continue
        projected = _normalized_latest_value(values.get(binding.key, KpiLatestValue.missing()))
        for destination_key in binding.destination_keys:
            destinations.setdefault(destination_key, {})[binding.key] = projected

    watermark = utc_iso(watermark_utc, field_name='watermark_utc')
    published_at = utc_iso(published_at_utc, field_name='published_at_utc')
    revision_payload = {
        'schema_version': 1,
        'configuration_revision': configuration.revision,
        'tool_projection_revision': configuration.tool_projection_revision,
        'watermark_utc': watermark,
        'destinations': {
            destination: {key: value.to_payload() for key, value in projected_values.items()}
            for destination, projected_values in destinations.items()
        },
    }
    manifest = KpiLatestManifest(
        schema_version=1,
        revision=canonical_revision(revision_payload),
        configuration_revision=configuration.revision,
        tool_projection_revision=configuration.tool_projection_revision,
        watermark_utc=watermark,
        published_at_utc=published_at,
    )
    return KpiLatestSnapshot(manifest=manifest, destinations=destinations)
