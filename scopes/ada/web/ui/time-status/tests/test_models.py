from datetime import UTC, datetime

import pytest

from ada.web.ui.time_status import (
    TimeStatusDefinitionError,
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
)


def _policy(*, warning: int = 200, stale: int = 300) -> TimeStatusFreshnessPolicy:
    return TimeStatusFreshnessPolicy(
        warning_after_seconds=warning,
        stale_after_seconds=stale,
    )


def _source(
    key: str,
    *,
    condition: TimeStatusSourceCondition = TimeStatusSourceCondition.FRESH,
    timestamp: datetime | None = datetime(2026, 8, 28, 22, 0, tzinfo=UTC),
    relative_age: str | None = 'hace más de 20 segundos',
    warning: int = 200,
    stale: int = 300,
) -> TimeStatusSourceState:
    if condition is TimeStatusSourceCondition.DATA_ERROR:
        timestamp = None
        relative_age = None
    return TimeStatusSourceState(
        key=key,
        label='PI' if key == 'pi' else 'Dispatch',
        policy=_policy(warning=warning, stale=stale),
        condition=condition,
        relative_age_text=relative_age,
        timestamp_utc=timestamp,
    )


def test_policy_requires_two_ordered_non_negative_thresholds() -> None:
    assert _policy() == TimeStatusFreshnessPolicy(200, 300)

    with pytest.raises(TimeStatusDefinitionError, match='non-negative'):
        _policy(warning=-1, stale=300)
    with pytest.raises(TimeStatusDefinitionError, match='greater than'):
        _policy(warning=300, stale=300)
    with pytest.raises(TimeStatusDefinitionError, match='greater than'):
        _policy(warning=301, stale=300)


def test_non_error_source_requires_timezone_aware_timestamp_and_relative_age() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='timezone-aware'):
        _source('pi', timestamp=datetime(2026, 8, 28, 22, 0))
    with pytest.raises(TimeStatusDefinitionError, match='relative age text'):
        _source('pi', relative_age=None)


def test_data_error_source_has_no_timestamp_or_relative_age() -> None:
    source = _source('pi', condition=TimeStatusSourceCondition.DATA_ERROR)

    assert source.timestamp_utc is None
    assert source.timestamp_iso is None
    assert source.relative_age_text is None


def test_ada_summary_requires_pi_and_accepts_optional_dispatch() -> None:
    pi = _source('pi')
    dispatch = _source('dispatch', warning=400, stale=600)

    assert TimeStatusSummaryState(pi=pi).required_sources == (pi,)
    assert TimeStatusSummaryState(pi=pi, dispatch=dispatch).required_sources == (pi, dispatch)

    with pytest.raises(TimeStatusDefinitionError, match='requires PI'):
        TimeStatusSummaryState(pi=_source('dispatch'))


def test_content_stale_uses_and_across_required_summary_sources() -> None:
    pi_hard = _source('pi', condition=TimeStatusSourceCondition.HARD_STALE)
    dispatch_fresh = _source('dispatch', warning=400, stale=600)
    dispatch_hard = _source(
        'dispatch',
        condition=TimeStatusSourceCondition.HARD_STALE,
        warning=400,
        stale=600,
    )

    assert TimeStatusSummaryState(pi=pi_hard).content_stale is True
    assert TimeStatusSummaryState(pi=pi_hard, dispatch=dispatch_fresh).content_stale is False
    assert TimeStatusSummaryState(pi=pi_hard, dispatch=dispatch_hard).content_stale is True


def test_data_error_is_separate_from_content_stale() -> None:
    pi_error = _source('pi', condition=TimeStatusSourceCondition.DATA_ERROR)
    dispatch_hard = _source(
        'dispatch',
        condition=TimeStatusSourceCondition.HARD_STALE,
        warning=400,
        stale=600,
    )
    state = TimeStatusSummaryState(pi=pi_error, dispatch=dispatch_hard)

    assert state.content_stale is False
    assert state.data_error_source_keys == ('pi',)


def _detail_source(key: str, *, value: str = '2026-08-29T22:00:00Z'):
    from ada.web.ui.time_status import TimeStatusDetailSourceState

    labels = {
        'pi': 'PI',
        'dispatch': 'Dispatch',
        'blockgrade': 'BlockGrade',
        'fabrica': 'Fábrica',
    }
    return TimeStatusDetailSourceState(
        key=key,
        label=labels.get(key, key),
        value=value,
    )


def test_detail_requires_pi_and_unique_consumed_source_keys() -> None:
    from ada.web.ui.time_status import TimeStatusDetailState

    with pytest.raises(TimeStatusDefinitionError, match='requires PI'):
        TimeStatusDetailState(sources=(_detail_source('blockgrade'),))
    with pytest.raises(TimeStatusDefinitionError, match='must be unique'):
        TimeStatusDetailState(sources=(_detail_source('pi'), _detail_source('pi')))


def test_detail_orders_control_sources_before_informational_sources() -> None:
    from ada.web.ui.time_status import TimeStatusDetailState

    state = TimeStatusDetailState(
        sources=(
            _detail_source('blockgrade'),
            _detail_source('dispatch'),
            _detail_source('fabrica'),
            _detail_source('pi'),
        )
    )

    assert tuple(source.key for source in state.sources) == (
        'pi',
        'dispatch',
        'blockgrade',
        'fabrica',
    )


def test_detail_source_authority_is_derived_only_from_pi_and_dispatch_identity() -> None:
    from ada.web.ui.time_status import TimeStatusDetailState

    state = TimeStatusDetailState(
        sources=(
            _detail_source('pi'),
            _detail_source('dispatch'),
            _detail_source('blockgrade', value='Error'),
        )
    )

    assert tuple(source.key for source in state.control_sources) == ('pi', 'dispatch')
    assert tuple(source.key for source in state.informational_sources) == ('blockgrade',)
    assert state.sources[2].is_control is False
