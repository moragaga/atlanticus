from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)
from ada.web.content_state.core import ContentState
from ada.web.content_state.dependency_resolver import ContentStateDependency
from ada.web.operational_state import AdaOperationalState, resolve_ada_operational_state
from ada.web.time_status.store_adapter import (
    TimeStatusSourceTimestamp,
    TimeStatusStoreSnapshot,
    TimeStatusTimestampQuality,
)
from ada.web.ui.time_status import (
    TimeStatusDetailSourceState,
    TimeStatusDetailState,
    TimeStatusSourceCondition,
)

_NOW = datetime(2026, 8, 30, 13, 0, tzinfo=UTC)


def _source_configuration(
    *,
    tool_key: str = 'process',
    with_dispatch: bool = False,
    additional_observation_source_keys: tuple[str, ...] = (),
    pi_pre_degrading_after_seconds: int = 200,
    pi_degrading_after_seconds: int = 300,
) -> tuple[ToolSourceConsumption, ToolSourceOperationalParticipation]:
    source_keys = ['pi']
    control_sources = [
        SourceControlPolicy(
            source_key='pi',
            pre_degrading_after_seconds=pi_pre_degrading_after_seconds,
            degrading_after_seconds=pi_degrading_after_seconds,
        )
    ]
    if with_dispatch:
        source_keys.append('dispatch')
        control_sources.append(
            SourceControlPolicy(
                source_key='dispatch',
                pre_degrading_after_seconds=400,
                degrading_after_seconds=600,
            )
        )
    source_keys.extend(additional_observation_source_keys)
    return (
        ToolSourceConsumption(tool_key=tool_key, source_keys=tuple(source_keys)),
        ToolSourceOperationalParticipation(
            tool_key=tool_key,
            control_sources=tuple(control_sources),
            additional_observation_source_keys=additional_observation_source_keys,
        ),
    )


def _timestamp(
    key: str,
    *,
    age_seconds: int | None = None,
    quality: TimeStatusTimestampQuality = TimeStatusTimestampQuality.VALID,
) -> TimeStatusSourceTimestamp:
    return TimeStatusSourceTimestamp(
        key=key,
        quality=quality,
        timestamp_utc=(
            _NOW - timedelta(seconds=age_seconds or 0)
            if quality is TimeStatusTimestampQuality.VALID
            else None
        ),
    )


def _snapshot(
    *,
    tool_key: str = 'process',
    pi_age_seconds: int = 10,
    pi_quality: TimeStatusTimestampQuality = TimeStatusTimestampQuality.VALID,
    dispatch_age_seconds: int | None = None,
    dispatch_quality: TimeStatusTimestampQuality = TimeStatusTimestampQuality.VALID,
) -> TimeStatusStoreSnapshot:
    sources = {
        'pi': _timestamp('pi', age_seconds=pi_age_seconds, quality=pi_quality),
    }
    if dispatch_age_seconds is not None or dispatch_quality is not TimeStatusTimestampQuality.VALID:
        sources['dispatch'] = _timestamp(
            'dispatch',
            age_seconds=dispatch_age_seconds,
            quality=dispatch_quality,
        )
    return TimeStatusStoreSnapshot(
        tool_key=tool_key,
        generated_at_utc=_NOW,
        sources=sources,
    )


def test_empty_resolution_is_explicit_and_ready() -> None:
    state = resolve_ada_operational_state(has_global_indicators=False)

    assert state == AdaOperationalState(
        tool_key=None,
        time_status_summary=None,
        global_indicators_runtime_state=ContentState.READY,
        global_indicators_source_keys=(),
    )


def test_control_thresholds_drive_time_status_and_content_state() -> None:
    consumption, participation = _source_configuration()

    state = resolve_ada_operational_state(
        has_global_indicators=True,
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
        time_status_snapshot=_snapshot(pi_age_seconds=240),
    )

    assert state.tool_key == 'process'
    assert state.time_status_summary is not None
    assert state.time_status_summary.pi.condition is TimeStatusSourceCondition.PREVENTIVE
    assert state.time_status_summary.pi.policy.warning_after_seconds == 200
    assert state.time_status_summary.pi.policy.stale_after_seconds == 300
    assert state.global_indicators_runtime_state is ContentState.READY
    assert state.global_indicators_source_keys == ('pi',)


def test_hard_stale_degrades_content_state() -> None:
    consumption, participation = _source_configuration()

    state = resolve_ada_operational_state(
        has_global_indicators=True,
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
        time_status_snapshot=_snapshot(pi_age_seconds=360),
    )

    assert state.time_status_summary is not None
    assert state.time_status_summary.pi.condition is TimeStatusSourceCondition.HARD_STALE
    assert state.global_indicators_runtime_state is ContentState.STALE


def test_dispatch_is_absent_when_not_configured() -> None:
    consumption, participation = _source_configuration()

    state = resolve_ada_operational_state(
        has_global_indicators=False,
        source_consumption=consumption,
        source_operational_participation=participation,
        time_status_snapshot=_snapshot(dispatch_age_seconds=700),
    )

    assert state.time_status_summary is not None
    assert state.time_status_summary.dispatch is None


def test_configured_dispatch_missing_from_snapshot_becomes_data_error() -> None:
    consumption, participation = _source_configuration(with_dispatch=True)

    state = resolve_ada_operational_state(
        has_global_indicators=False,
        source_consumption=consumption,
        source_operational_participation=participation,
        time_status_snapshot=_snapshot(),
    )

    assert state.time_status_summary is not None
    assert state.time_status_summary.dispatch is not None
    assert state.time_status_summary.dispatch.condition is TimeStatusSourceCondition.DATA_ERROR


def test_additional_observation_does_not_become_control_dependency() -> None:
    consumption, participation = _source_configuration(
        additional_observation_source_keys=('blockgrade',)
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="not declared as CONTROL: 'blockgrade'",
    ):
        resolve_ada_operational_state(
            has_global_indicators=True,
            content_state_dependencies=(
                ContentStateDependency(
                    component_key='global_indicators',
                    source_keys=('blockgrade',),
                ),
            ),
            source_consumption=consumption,
            source_operational_participation=participation,
            time_status_snapshot=_snapshot(),
        )


def test_time_status_detail_requires_declared_additional_observation_source() -> None:
    consumption = ToolSourceConsumption(
        tool_key='process',
        source_keys=('pi', 'blockgrade'),
    )
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='not declared as ADDITIONAL OBSERVATION',
    ):
        resolve_ada_operational_state(
            has_global_indicators=False,
            source_consumption=consumption,
            source_operational_participation=participation,
            time_status_snapshot=_snapshot(),
            time_status_detail=TimeStatusDetailState(
                sources=(
                    TimeStatusDetailSourceState(
                        key='blockgrade',
                        label='BlockGrade',
                        value='Error',
                    ),
                )
            ),
        )


def test_source_driven_resolution_requires_consumption_and_participation() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='requires ToolSourceConsumption',
    ):
        resolve_ada_operational_state(
            has_global_indicators=False,
            time_status_snapshot=_snapshot(),
        )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='requires ToolSourceOperationalParticipation',
    ):
        resolve_ada_operational_state(
            has_global_indicators=False,
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            time_status_snapshot=_snapshot(),
        )


def test_only_global_indicators_is_supported_by_current_content_state_contract() -> None:
    with pytest.raises(ValueError, match='Unsupported Generic Application Content State component'):
        resolve_ada_operational_state(
            has_global_indicators=False,
            content_state_dependencies=(
                ContentStateDependency(component_key='other_component', source_keys=('pi',)),
            ),
        )


def test_global_indicator_dependency_requires_component_existence() -> None:
    with pytest.raises(ValueError, match='requires Global Indicators'):
        resolve_ada_operational_state(
            has_global_indicators=False,
            content_state_dependencies=(
                ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
            ),
        )


def test_operational_state_package_has_no_dash_or_io_runtime_dependency() -> None:
    from pathlib import Path

    source = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'operational_state' / 'resolver.py'
    ).read_text(encoding='utf-8')

    assert 'from dash' not in source
    assert 'import dash' not in source
    assert 'requests' not in source
    assert 'httpx' not in source
    assert 'cosmos' not in source.lower()
    assert 'filesystem' not in source.lower()
