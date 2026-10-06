# Traduce exclusivamente el system store time_status a estados semánticos de la UI.
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from ada.contracts.tools.sources import SourceControlPolicy
from ada.web.kpis.collector import (
    KpiLatestValueState,
    decode_kpi_latest_value,
)
from ada.web.ui.time_status import (
    TimeStatusFreshnessPolicy,
    TimeStatusSourceState,
    TimeStatusSummaryState,
    resolve_time_status_source_state,
)

from .binding import TimeStatusRuntimeBinding

_TIME_STATUS_DESTINATION_KEY = 'time_status'
_SOURCE_LABELS = {'pi': 'PI', 'dispatch': 'Dispatch'}


def resolve_time_status_summary(
    store_data: object,
    *,
    binding: TimeStatusRuntimeBinding,
    now_utc: datetime | None = None,
) -> TimeStatusSummaryState:
    if not isinstance(binding, TimeStatusRuntimeBinding):
        raise TypeError('binding must be TimeStatusRuntimeBinding')
    values = _latest_values(store_data, tool_key=binding.tool_key)
    pi_policy = binding.participation.control_policy('pi')
    if pi_policy is None:
        raise RuntimeError('Validated Time Status binding is missing PI control policy')
    dispatch_policy = binding.participation.control_policy('dispatch')
    return TimeStatusSummaryState(
        pi=_resolve_source(values, policy=pi_policy, now_utc=now_utc),
        dispatch=(
            None
            if dispatch_policy is None
            else _resolve_source(values, policy=dispatch_policy, now_utc=now_utc)
        ),
        has_detail=True,
    )


def _latest_values(store_data: object, *, tool_key: str) -> Mapping[str, object] | None:
    if not isinstance(store_data, Mapping):
        return None
    if store_data.get('tool_key') != tool_key:
        return None
    if store_data.get('destination_key') != _TIME_STATUS_DESTINATION_KEY:
        return None
    latest = store_data.get('latest')
    if not isinstance(latest, Mapping):
        return None
    values = latest.get('values')
    return values if isinstance(values, Mapping) else None


def _resolve_source(
    values: Mapping[str, object] | None,
    *,
    policy: SourceControlPolicy,
    now_utc: datetime | None,
) -> TimeStatusSourceState:
    present = values is not None and policy.source_key in values
    entry = None if values is None else values.get(policy.source_key)
    decoded = decode_kpi_latest_value(entry, present=present)
    timestamp = _decoded_timestamp(decoded.state, decoded.value_kind, decoded.value)
    return resolve_time_status_source_state(
        key=policy.source_key,
        label=_SOURCE_LABELS[policy.source_key],
        policy=TimeStatusFreshnessPolicy(
            warning_after_seconds=policy.pre_degrading_after_seconds,
            stale_after_seconds=policy.degrading_after_seconds,
        ),
        timestamp_utc=timestamp,
        now_utc=now_utc,
    )


def _decoded_timestamp(
    state: KpiLatestValueState,
    value_kind: str | None,
    value: object,
) -> datetime | None:
    if state is not KpiLatestValueState.OK or value_kind != 'value':
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    normalized = f'{value[:-1]}+00:00' if value.endswith('Z') else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)
