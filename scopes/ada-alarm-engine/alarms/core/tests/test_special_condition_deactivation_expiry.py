from datetime import timedelta

from ada.alarms.core import (
    AlarmStatus,
    GroupLifecycleState,
    ManagementEffectChangeKind,
    PriorityDisposition,
    ReappearanceChange,
    reduce_group_cycle,
)

from .support import NOW, Ids, identity, management_action, physical, plan, reappear_after


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


def _start_special(ids: Ids):
    special = plan(
        'special',
        is_special_condition=True,
        priority_order=1,
        deactivation_approval_required=False,
    )
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        (special,),
        (physical('special', AlarmStatus.ACTIVE),),
        ids=ids,
    )
    return special, started


def _manage_and_deactivate(
    special,
    started,
    ids: Ids,
    *,
    managed_at,
    deactivation_until,
    reappearance_seconds=300,
):
    runtime = started.state.get(identity('special'))
    assert runtime is not None
    assert runtime.occurrence is not None
    return _reduce(
        started.state,
        (special,),
        (physical('special', AlarmStatus.ACTIVE, at=managed_at),),
        at=managed_at,
        actions=(
            management_action(
                'special',
                occurrence_id=runtime.occurrence.occurrence_id,
                at=managed_at,
                deactivation_until=deactivation_until,
            ),
        ),
        ids=ids,
        reappearance_seconds=reappearance_seconds,
    )


def test_active_special_condition_reappears_when_deactivation_expires_before_timer() -> None:
    ids = Ids()
    special, started = _start_special(ids)
    managed_at = NOW + timedelta(minutes=1)
    deactivation_until = managed_at + timedelta(minutes=2)
    managed = _manage_and_deactivate(
        special,
        started,
        ids,
        managed_at=managed_at,
        deactivation_until=deactivation_until,
        reappearance_seconds=300,
    )

    decision = _reduce(
        managed.state,
        (special,),
        (physical('special', AlarmStatus.ACTIVE, at=deactivation_until),),
        at=deactivation_until,
        ids=ids,
        reappearance_seconds=300,
    )

    runtime = decision.state.get(identity('special'))
    assert runtime is not None
    assert runtime.occurrence is not None
    assert runtime.deactivation_effect is None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert decision.reappearance_changes == (
        ReappearanceChange(
            alarm_identity=identity('special'),
            occurrence_id=runtime.occurrence.occurrence_id,
            effective_at=deactivation_until,
            management_cycle=2,
        ),
    )
    assert [
        change.kind
        for change in decision.management_effect_changes
        if change.alarm_identity == identity('special')
    ] == [ManagementEffectChangeKind.CLEARED]
    assert decision.priority_resolution is not None
    assert decision.priority_resolution.alarms[0].disposition is PriorityDisposition.PREDOMINANT


def test_inactive_special_condition_does_not_reappear_when_deactivation_expires() -> None:
    ids = Ids()
    special, started = _start_special(ids)
    managed_at = NOW + timedelta(minutes=1)
    deactivation_until = managed_at + timedelta(minutes=2)
    managed = _manage_and_deactivate(
        special,
        started,
        ids,
        managed_at=managed_at,
        deactivation_until=deactivation_until,
    )

    decision = _reduce(
        managed.state,
        (special,),
        (physical('special', AlarmStatus.INACTIVE, at=deactivation_until),),
        at=deactivation_until,
        ids=ids,
    )

    assert decision.reappearance_changes == ()
    assert decision.state.episode is None
    assert decision.state.get(identity('special')) is None


def test_error_special_condition_does_not_reappear_when_deactivation_expires() -> None:
    ids = Ids()
    special, started = _start_special(ids)
    managed_at = NOW + timedelta(minutes=1)
    deactivation_until = managed_at + timedelta(minutes=2)
    managed = _manage_and_deactivate(
        special,
        started,
        ids,
        managed_at=managed_at,
        deactivation_until=deactivation_until,
    )

    from .support import error

    decision = _reduce(
        managed.state,
        (special,),
        (error('special', at=deactivation_until),),
        at=deactivation_until,
        ids=ids,
    )

    runtime = decision.state.get(identity('special'))
    assert runtime is not None
    assert runtime.deactivation_effect is None
    assert runtime.management_effect is not None
    assert decision.reappearance_changes == ()


def test_special_condition_timer_and_deactivation_expiry_same_cycle_reappear_once() -> None:
    ids = Ids()
    special, started = _start_special(ids)
    managed_at = NOW + timedelta(minutes=1)
    due = managed_at + timedelta(minutes=5)
    managed = _manage_and_deactivate(
        special,
        started,
        ids,
        managed_at=managed_at,
        deactivation_until=due,
        reappearance_seconds=300,
    )

    decision = _reduce(
        managed.state,
        (special,),
        (physical('special', AlarmStatus.ACTIVE, at=due),),
        at=due,
        ids=ids,
        reappearance_seconds=300,
    )

    runtime = decision.state.get(identity('special'))
    assert runtime is not None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert len(decision.reappearance_changes) == 1
    assert decision.reappearance_changes[0].effective_at == due
