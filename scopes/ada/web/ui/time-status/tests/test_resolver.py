from datetime import UTC, datetime, timedelta, timezone

import pytest

from ada.web.ui.time_status import (
    TimeStatusDefinitionError,
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    format_time_status_relative_age,
    resolve_time_status_condition,
    resolve_time_status_source_state,
)


@pytest.mark.parametrize(
    ('age_seconds', 'expected'),
    [
        (0, 'hace menos de 10 segundos'),
        (9, 'hace menos de 10 segundos'),
        (10, 'hace más de 10 segundos'),
        (19, 'hace más de 10 segundos'),
        (20, 'hace más de 20 segundos'),
        (59, 'hace más de 50 segundos'),
        (60, 'hace más de 1 minuto'),
        (119, 'hace más de 1 minuto'),
        (120, 'hace más de 2 minutos'),
        (3_600, 'hace más de 1 hora'),
        (7_200, 'hace más de 2 horas'),
        (86_400, 'hace más de 1 día'),
        (172_800, 'hace más de 2 días'),
    ],
)
def test_relative_age_uses_discrete_buckets(age_seconds: int, expected: str) -> None:
    assert format_time_status_relative_age(age_seconds) == expected


@pytest.mark.parametrize(
    ('age_seconds', 'expected'),
    [
        (199, TimeStatusSourceCondition.FRESH),
        (200, TimeStatusSourceCondition.PREVENTIVE),
        (299, TimeStatusSourceCondition.PREVENTIVE),
        (300, TimeStatusSourceCondition.HARD_STALE),
    ],
)
def test_pi_policy_boundaries_are_inclusive_on_transition(
    age_seconds: int,
    expected: TimeStatusSourceCondition,
) -> None:
    policy = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)

    assert resolve_time_status_condition(age_seconds=age_seconds, policy=policy) is expected


@pytest.mark.parametrize(
    ('age_seconds', 'expected'),
    [
        (399, TimeStatusSourceCondition.FRESH),
        (400, TimeStatusSourceCondition.PREVENTIVE),
        (599, TimeStatusSourceCondition.PREVENTIVE),
        (600, TimeStatusSourceCondition.HARD_STALE),
    ],
)
def test_dispatch_policy_uses_its_own_thresholds(
    age_seconds: int,
    expected: TimeStatusSourceCondition,
) -> None:
    policy = TimeStatusFreshnessPolicy(warning_after_seconds=400, stale_after_seconds=600)

    assert resolve_time_status_condition(age_seconds=age_seconds, policy=policy) is expected


def test_source_state_is_resolved_from_real_now_without_new_watermark() -> None:
    policy = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)
    timestamp = datetime(2026, 8, 29, 20, 0, tzinfo=UTC)

    fresh = resolve_time_status_source_state(
        key='pi',
        label='PI',
        policy=policy,
        timestamp_utc=timestamp,
        now_utc=timestamp + timedelta(seconds=199),
    )
    preventive = resolve_time_status_source_state(
        key='pi',
        label='PI',
        policy=policy,
        timestamp_utc=timestamp,
        now_utc=timestamp + timedelta(seconds=200),
    )
    hard = resolve_time_status_source_state(
        key='pi',
        label='PI',
        policy=policy,
        timestamp_utc=timestamp,
        now_utc=timestamp + timedelta(seconds=300),
    )

    assert [fresh.condition, preventive.condition, hard.condition] == [
        TimeStatusSourceCondition.FRESH,
        TimeStatusSourceCondition.PREVENTIVE,
        TimeStatusSourceCondition.HARD_STALE,
    ]


@pytest.mark.parametrize(
    'timestamp',
    [
        None,
        datetime(2026, 8, 29, 20, 0),
    ],
)
def test_missing_or_naive_timestamp_is_data_error(timestamp: datetime | None) -> None:
    state = resolve_time_status_source_state(
        key='pi',
        label='PI',
        policy=TimeStatusFreshnessPolicy(200, 300),
        timestamp_utc=timestamp,
        now_utc=datetime(2026, 8, 29, 20, 5, tzinfo=UTC),
    )

    assert state.condition is TimeStatusSourceCondition.DATA_ERROR
    assert state.relative_age_text is None


def test_future_timestamp_is_data_error_without_hidden_skew_tolerance() -> None:
    now = datetime(2026, 8, 29, 20, 5, tzinfo=UTC)
    future = now + timedelta(seconds=1)

    state = resolve_time_status_source_state(
        key='dispatch',
        label='Dispatch',
        policy=TimeStatusFreshnessPolicy(400, 600),
        timestamp_utc=future,
        now_utc=now,
    )

    assert state.condition is TimeStatusSourceCondition.DATA_ERROR
    assert state.timestamp_utc == future
    assert state.relative_age_text is None


def test_resolver_rejects_informational_source_keys() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='only PI and Dispatch'):
        resolve_time_status_source_state(
            key='blockgrade',
            label='BlockGrade',
            policy=TimeStatusFreshnessPolicy(200, 300),
            timestamp_utc=datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
            now_utc=datetime(2026, 8, 29, 20, 1, tzinfo=UTC),
        )


def test_resolver_normalizes_aware_offsets_to_utc() -> None:
    source_tz = timezone(timedelta(hours=-4))
    timestamp = datetime(2026, 8, 29, 16, 0, tzinfo=source_tz)

    state = resolve_time_status_source_state(
        key='pi',
        label='PI',
        policy=TimeStatusFreshnessPolicy(200, 300),
        timestamp_utc=timestamp,
        now_utc=datetime(2026, 8, 29, 20, 1, tzinfo=UTC),
    )

    assert state.timestamp_utc == datetime(2026, 8, 29, 20, 0, tzinfo=UTC)
    assert state.condition is TimeStatusSourceCondition.FRESH


def test_resolver_rejects_naive_now() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='now_utc must be timezone-aware'):
        resolve_time_status_source_state(
            key='pi',
            label='PI',
            policy=TimeStatusFreshnessPolicy(200, 300),
            timestamp_utc=datetime(2026, 8, 29, 20, 0, tzinfo=UTC),
            now_utc=datetime(2026, 8, 29, 20, 1),
        )


@pytest.mark.parametrize('value', [-1, True, 1.5])
def test_relative_age_rejects_invalid_age(value: object) -> None:
    with pytest.raises(TimeStatusDefinitionError, match='age_seconds'):
        format_time_status_relative_age(value)
