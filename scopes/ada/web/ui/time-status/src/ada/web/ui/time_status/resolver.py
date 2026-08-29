from __future__ import annotations

from datetime import UTC, datetime

from .errors import TimeStatusDefinitionError
from .models import (
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
)

_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


def resolve_time_status_source_state(
    *,
    key: str,
    label: str,
    policy: TimeStatusFreshnessPolicy,
    timestamp_utc: datetime | None,
    now_utc: datetime | None = None,
) -> TimeStatusSourceState:
    if key not in _CONTROL_SOURCE_KEYS:
        raise TimeStatusDefinitionError('Freshness resolver supports only PI and Dispatch sources')

    now = _normalize_now(now_utc)
    timestamp = _normalize_timestamp(timestamp_utc)
    if timestamp is None:
        return TimeStatusSourceState(
            key=key,
            label=label,
            policy=policy,
            condition=TimeStatusSourceCondition.DATA_ERROR,
            relative_age_text=None,
            timestamp_utc=None,
        )

    if timestamp > now:
        return TimeStatusSourceState(
            key=key,
            label=label,
            policy=policy,
            condition=TimeStatusSourceCondition.DATA_ERROR,
            relative_age_text=None,
            timestamp_utc=timestamp,
        )

    age_seconds = int((now - timestamp).total_seconds())
    condition = resolve_time_status_condition(age_seconds=age_seconds, policy=policy)
    return TimeStatusSourceState(
        key=key,
        label=label,
        policy=policy,
        condition=condition,
        relative_age_text=format_time_status_relative_age(age_seconds),
        timestamp_utc=timestamp,
    )


def resolve_time_status_condition(
    *,
    age_seconds: int,
    policy: TimeStatusFreshnessPolicy,
) -> TimeStatusSourceCondition:
    _require_age(age_seconds)
    if age_seconds >= policy.stale_after_seconds:
        return TimeStatusSourceCondition.HARD_STALE
    if age_seconds >= policy.warning_after_seconds:
        return TimeStatusSourceCondition.PREVENTIVE
    return TimeStatusSourceCondition.FRESH


def format_time_status_relative_age(age_seconds: int) -> str:
    _require_age(age_seconds)
    if age_seconds < 10:
        return 'hace menos de 10 segundos'
    if age_seconds < 60:
        bucket = (age_seconds // 10) * 10
        return f'hace más de {bucket} segundos'
    if age_seconds < 3_600:
        minutes = age_seconds // 60
        unit = 'minuto' if minutes == 1 else 'minutos'
        return f'hace más de {minutes} {unit}'
    if age_seconds < 86_400:
        hours = age_seconds // 3_600
        unit = 'hora' if hours == 1 else 'horas'
        return f'hace más de {hours} {unit}'
    days = age_seconds // 86_400
    unit = 'día' if days == 1 else 'días'
    return f'hace más de {days} {unit}'


def _normalize_now(value: datetime | None) -> datetime:
    now = value or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise TimeStatusDefinitionError('now_utc must be timezone-aware')
    return now.astimezone(UTC)


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TimeStatusDefinitionError('timestamp_utc must be a datetime or None')
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def _require_age(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TimeStatusDefinitionError('age_seconds must be an integer')
    if value < 0:
        raise TimeStatusDefinitionError('age_seconds must be non-negative')
