from datetime import timedelta

from ada_command_center.alarms.core import (
    AlarmStatus,
    GroupLifecycleState,
    PriorityDisposition,
    reduce_group_cycle,
)
from ada_command_center.domain.alarms import AlarmKind

from .support import (
    NOW,
    Ids,
    identity,
    management_action,
    physical,
    plan,
    reappear_after,
)


def _reduce(
    state: GroupLifecycleState,
    plans,
    evaluations,
    *,
    at=NOW,
    actions=(),
    ids: Ids | None = None,
    reappearance_seconds=300,
):
    generated = ids or Ids()
    return reduce_group_cycle(
        state,
        cycle_at=at,
        planned_alarms=plans,
        evaluations=evaluations,
        management_actions=actions,
        occurrence_id_factory=generated.new_occurrence,
        episode_id_factory=generated.new_episode,
        management_effect_id_factory=generated.new_management_effect,
        reappearance_due_at_resolver=reappear_after(reappearance_seconds),
        deactivation_request_id_factory=generated.new_deactivation_request,
        deactivation_effect_id_factory=generated.new_deactivation_effect,
    )


def _occurrence_id(decision, alarm_key: str) -> str:
    runtime = decision.state.get(identity(alarm_key))
    assert runtime is not None
    assert runtime.occurrence is not None
    return runtime.occurrence.occurrence_id


def _disposition(decision, alarm_key: str):
    resolution = decision.priority_resolution
    assert resolution is not None
    return next(
        item.disposition for item in resolution.alarms if item.alarm_identity == identity(alarm_key)
    )


def test_deactivation_keeps_lower_rank_suppressed_after_management_timer_expires() -> None:
    plans = (
        plan(
            'impact',
            kind=AlarmKind.IMPACT,
            priority_order=1,
            deactivation_approval_required=False,
        ),
        plan('risk', kind=AlarmKind.RISK, priority_order=2),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('impact', AlarmStatus.ACTIVE),
            physical('risk', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )
    managed_at = NOW + timedelta(minutes=1)
    deactivation_until = managed_at + timedelta(hours=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('impact', AlarmStatus.ACTIVE, at=managed_at),
            physical('risk', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'impact',
                occurrence_id=_occurrence_id(started, 'impact'),
                at=managed_at,
                deactivation_until=deactivation_until,
            ),
        ),
        ids=ids,
        reappearance_seconds=300,
    )
    due = managed_at + timedelta(minutes=5)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('impact', AlarmStatus.ACTIVE, at=due),
            physical('risk', AlarmStatus.ACTIVE, at=due),
        ),
        at=due,
        ids=ids,
        reappearance_seconds=300,
    )

    source = decision.state.get(identity('impact'))
    assert source is not None
    assert source.management_effect is None
    assert source.deactivation_effect is not None
    assert decision.reappearance_changes == ()
    suppression = next(
        item
        for item in decision.cascade_suppressions
        if item.target_alarm_identity == identity('risk')
    )
    assert suppression.management_effect_id is None
    assert suppression.deactivation_effect_id == source.deactivation_effect.effect_id
    assert _disposition(decision, 'risk') is PriorityDisposition.CASCADE_SUPPRESSED


def test_special_condition_does_not_cross_active_deactivation_scope() -> None:
    plans = (
        plan(
            'alarm',
            kind=AlarmKind.IMPACT,
            priority_order=1,
            deactivation_approval_required=False,
            reappearance_special_conditions=(identity('special'),),
        ),
        plan('special', kind=AlarmKind.IMPACT, priority_order=2),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE),
            physical('special', AlarmStatus.INACTIVE),
        ),
        ids=ids,
    )
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=managed_at),
            physical('special', AlarmStatus.INACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'alarm',
                occurrence_id=_occurrence_id(started, 'alarm'),
                at=managed_at,
                deactivation_until=managed_at + timedelta(hours=8),
            ),
        ),
        ids=ids,
        reappearance_seconds=3600,
    )
    special_at = managed_at + timedelta(hours=2)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=special_at),
            physical('special', AlarmStatus.ACTIVE, at=special_at),
        ),
        at=special_at,
        ids=ids,
        reappearance_seconds=3600,
    )

    source = decision.state.get(identity('alarm'))
    assert source is not None
    assert source.management_effect is None
    assert source.deactivation_effect is not None
    assert decision.reappearance_changes == ()
    suppression = next(
        item
        for item in decision.cascade_suppressions
        if item.target_alarm_identity == identity('special')
    )
    assert suppression.management_effect_id is None
    assert suppression.deactivation_effect_id == source.deactivation_effect.effect_id
    assert _disposition(decision, 'special') is PriorityDisposition.CASCADE_SUPPRESSED
