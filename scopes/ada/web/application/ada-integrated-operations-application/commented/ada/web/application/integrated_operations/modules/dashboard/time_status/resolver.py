# El adaptador usa el System Store ya refrescado por Collector; no crea polling adicional.
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.time_status.runtime import TimeStatusDetailProvider
from ada.web.ui.time_status import TimeStatusDetailSourceState, TimeStatusDetailState

from .bindings import DashboardTimeStatusSourceBinding

_MISSING_TEXT = 'Sin información temporal disponible'


def create_dashboard_time_status_detail_provider(
    tool_key: str,
    sources: tuple[DashboardTimeStatusSourceBinding, ...],
) -> TimeStatusDetailProvider:
    if not isinstance(tool_key, str) or not tool_key or tool_key != tool_key.strip():
        raise ValueError('Time Status tool_key is invalid')
    if not isinstance(sources, tuple) or not sources:
        raise ValueError('Time Status sources must be a non-empty tuple')
    if any(not isinstance(source, DashboardTimeStatusSourceBinding) for source in sources):
        raise TypeError('Time Status sources must contain DashboardTimeStatusSourceBinding values')
    keys = tuple(source.source_key for source in sources)
    if len(set(keys)) != len(keys):
        raise ValueError('Time Status source keys must be unique')

    def resolve(store_data: object) -> TimeStatusDetailState:
        values = _latest_values(store_data, tool_key)
        return TimeStatusDetailState(
            sources=tuple(
                TimeStatusDetailSourceState(
                    key=source.source_key,
                    label=source.label,
                    value=_MISSING_TEXT,
                    timestamp_utc=_timestamp(values, source.latest_kpi_key),
                )
                for source in sources
            )
        )

    return TimeStatusDetailProvider(source_keys=keys, resolve=resolve)


def _latest_values(store_data: object, tool_key: str) -> Mapping[str, object] | None:
    if not isinstance(store_data, Mapping):
        return None
    if store_data.get('tool_key') != tool_key or store_data.get('destination_key') != 'time_status':
        return None
    latest = store_data.get('latest')
    if not isinstance(latest, Mapping):
        return None
    values = latest.get('values')
    return values if isinstance(values, Mapping) else None


def _timestamp(values: Mapping[str, object] | None, key: str) -> datetime | None:
    if values is None:
        return None
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is not KpiLatestValueState.OK or decoded.value_kind != 'value':
        return None
    if decoded.value_type != 'text' or not isinstance(decoded.value, str):
        return None
    value = decoded.value
    if not value or value != value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp.astimezone(UTC)
