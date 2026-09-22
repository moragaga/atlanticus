from datetime import timedelta

from ada_command_center.alarms.core import (
    AlarmKind,
    AlarmStatus,
    GroupLifecycleState,
    ReappearanceChange,
    reduce_group_cycle,
)

from .support import (
    NOW,
    Ids,
    error,
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
    reappearance_seconds=3600,
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
    )


def _occurrence_id(decision, alarm_key: str) -> str:
    runtime = decision.state.get(identity(alarm_key))
    assert runtime is not None
    assert runtime.occurrence is not None
    return runtime.occurrence.occurrence_id


def _start_managed_alarm_with_inactive_special(
    ids: Ids,
    *,
    reappearance_seconds: int = 3600,
    reappearance_special_conditions=(),
):
    plans = (
        plan(
            'alarm',
            kind=AlarmKind.IMPACT,
            priority_order=1,
            reappearance_special_conditions=reappearance_special_conditions,
        ),
        plan('special', kind=AlarmKind.IMPACT, priority_order=2),
    )
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
            ),
        ),
        ids=ids,
        reappearance_seconds=reappearance_seconds,
    )
    return plans, managed, managed_at


def test_unreferenced_active_lower_rank_alarm_does_not_release_management_effect() -> None:
    ids = Ids()
    plans, managed, managed_at = _start_managed_alarm_with_inactive_special(ids)
    active_at = managed_at + timedelta(minutes=1)

    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=active_at),
            physical('special', AlarmStatus.ACTIVE, at=active_at),
        ),
        at=active_at,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is not None
    assert decision.reappearance_changes == ()


def test_inactive_lower_rank_alarm_does_not_release_management_effect() -> None:
    ids = Ids()
    plans, managed, managed_at = _start_managed_alarm_with_inactive_special(
        ids,
        reappearance_special_conditions=(identity('special'),),
    )
    at = managed_at + timedelta(minutes=1)

    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=at),
            physical('special', AlarmStatus.INACTIVE, at=at),
        ),
        at=at,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is not None
    assert decision.reappearance_changes == ()


def test_error_lower_rank_alarm_does_not_release_management_effect() -> None:
    ids = Ids()
    plans, managed, managed_at = _start_managed_alarm_with_inactive_special(
        ids,
        reappearance_special_conditions=(identity('special'),),
    )
    at = managed_at + timedelta(minutes=1)

    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=at),
            error('special', at=at),
        ),
        at=at,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is not None
    assert decision.reappearance_changes == ()


def test_timer_due_reappears_once_even_if_another_alarm_activates_same_cycle() -> None:
    ids = Ids()
    plans, managed, managed_at = _start_managed_alarm_with_inactive_special(
        ids,
        reappearance_seconds=300,
        reappearance_special_conditions=(identity('special'),),
    )
    due = managed_at + timedelta(minutes=5)

    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=due),
            physical('special', AlarmStatus.ACTIVE, at=due),
        ),
        at=due,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.occurrence is not None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert decision.reappearance_changes == (
        ReappearanceChange(
            alarm_identity=identity('alarm'),
            occurrence_id=runtime.occurrence.occurrence_id,
            effective_at=due,
            management_cycle=2,
        ),
    )


def test_closed_managed_occurrence_is_not_resurrected_by_later_alarm_activation() -> None:
    plans = (
        plan(
            'alarm',
            kind=AlarmKind.IMPACT,
            priority_order=1,
            reappearance_special_conditions=(identity('special'),),
        ),
        plan('blocker', kind=AlarmKind.IMPACT, priority_order=2),
        plan('special', kind=AlarmKind.IMPACT, priority_order=3),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE),
            physical('blocker', AlarmStatus.ACTIVE),
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
            physical('blocker', AlarmStatus.ACTIVE, at=managed_at),
            physical('special', AlarmStatus.INACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'alarm',
                occurrence_id=_occurrence_id(started, 'alarm'),
                at=managed_at,
            ),
        ),
        ids=ids,
    )
    closed_at = managed_at + timedelta(minutes=1)
    closed = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.INACTIVE, at=closed_at),
            physical('blocker', AlarmStatus.ACTIVE, at=closed_at),
            physical('special', AlarmStatus.INACTIVE, at=closed_at),
        ),
        at=closed_at,
        ids=ids,
    )

    source = closed.state.get(identity('alarm'))
    assert source is not None
    assert source.occurrence is None
    assert source.management_effect is not None

    special_at = closed_at + timedelta(minutes=1)
    decision = _reduce(
        closed.state,
        plans,
        (
            physical('alarm', AlarmStatus.INACTIVE, at=special_at),
            physical('blocker', AlarmStatus.ACTIVE, at=special_at),
            physical('special', AlarmStatus.ACTIVE, at=special_at),
        ),
        at=special_at,
        ids=ids,
    )

    source = decision.state.get(identity('alarm'))
    assert source is not None
    assert source.occurrence is None
    assert source.management_effect is not None
    assert not any(
        change.alarm_identity == identity('alarm') for change in decision.reappearance_changes
    )


def test_referenced_special_activation_reappears_managed_alarm_before_timer() -> None:
    ids = Ids()
    plans, managed, managed_at = _start_managed_alarm_with_inactive_special(
        ids,
        reappearance_special_conditions=(identity('special'),),
    )

    active_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=active_at),
            physical('special', AlarmStatus.ACTIVE, at=active_at),
        ),
        at=active_at,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.occurrence is not None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert decision.reappearance_changes == (
        ReappearanceChange(
            alarm_identity=identity('alarm'),
            occurrence_id=runtime.occurrence.occurrence_id,
            effective_at=active_at,
            management_cycle=2,
        ),
    )


def test_referenced_special_triggers_even_when_priority_suppressed() -> None:
    plans = (
        plan(
            'alarm',
            kind=AlarmKind.IMPACT,
            priority_order=1,
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
            ),
        ),
        ids=ids,
    )

    active_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=active_at),
            physical('special', AlarmStatus.ACTIVE, at=active_at),
        ),
        at=active_at,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is None
    assert len(decision.reappearance_changes) == 1
    assert not any(
        suppression.target_alarm_identity == identity('special')
        for suppression in decision.cascade_suppressions
    )


def test_any_referenced_special_condition_can_trigger_reappearance() -> None:
    plans = (
        plan(
            'alarm',
            kind=AlarmKind.IMPACT,
            priority_order=1,
            reappearance_special_conditions=(
                identity('special-a'),
                identity('special-b'),
            ),
        ),
        plan('special-a', kind=AlarmKind.IMPACT, priority_order=2),
        plan('special-b', kind=AlarmKind.IMPACT, priority_order=3),
    )

    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE),
            physical('special-a', AlarmStatus.INACTIVE),
            physical('special-b', AlarmStatus.INACTIVE),
        ),
        ids=ids,
    )
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=managed_at),
            physical('special-a', AlarmStatus.INACTIVE, at=managed_at),
            physical('special-b', AlarmStatus.INACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'alarm',
                occurrence_id=_occurrence_id(started, 'alarm'),
                at=managed_at,
            ),
        ),
        ids=ids,
    )

    active_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('alarm', AlarmStatus.ACTIVE, at=active_at),
            physical('special-a', AlarmStatus.INACTIVE, at=active_at),
            physical('special-b', AlarmStatus.ACTIVE, at=active_at),
        ),
        at=active_at,
        ids=ids,
    )

    runtime = decision.state.get(identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is None
    assert len(decision.reappearance_changes) == 1
