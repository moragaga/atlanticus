from datetime import timedelta

from ada.alarms.core import (
    AlarmStatus,
    GroupLifecycleState,
    PriorityDisposition,
    reduce_group_cycle,
)
from ada.contracts.alarms import AlarmKind

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
    )


def _occurrence_id(decision, alarm_key: str) -> str:
    runtime = decision.state.get(identity(alarm_key))
    assert runtime is not None
    assert runtime.occurrence is not None
    return runtime.occurrence.occurrence_id


def _dispositions(decision):
    resolution = decision.priority_resolution
    assert resolution is not None
    return {item.alarm_identity: item for item in resolution.alarms}


def test_special_condition_without_management_competes_only_by_priority_order() -> None:
    plans = (
        plan(
            'special',
            kind=AlarmKind.RISK,
            is_special_condition=True,
            priority_order=2,
        ),
        plan('rule', kind=AlarmKind.IMPACT, priority_order=1),
    )
    decision = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('special', AlarmStatus.ACTIVE),
            physical('rule', AlarmStatus.ACTIVE),
        ),
    )

    resolution = decision.priority_resolution
    assert resolution is not None
    assert resolution.predominant_alarm_identity == identity('rule')
    dispositions = _dispositions(decision)
    assert dispositions[identity('rule')].disposition is PriorityDisposition.PREDOMINANT
    assert dispositions[identity('special')].disposition is PriorityDisposition.ECLIPSED


def test_managed_predominant_special_condition_suppresses_all_lower_active_rules() -> None:
    plans = (
        plan(
            'special',
            kind=AlarmKind.RISK,
            is_special_condition=True,
            priority_order=1,
        ),
        plan('rule-a', kind=AlarmKind.IMPACT, priority_order=2),
        plan('rule-b', kind=AlarmKind.RISK, priority_order=3),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('special', AlarmStatus.ACTIVE),
            physical('rule-a', AlarmStatus.ACTIVE),
            physical('rule-b', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        plans,
        (
            physical('special', AlarmStatus.ACTIVE, at=managed_at),
            physical('rule-a', AlarmStatus.ACTIVE, at=managed_at),
            physical('rule-b', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'special',
                occurrence_id=_occurrence_id(started, 'special'),
                at=managed_at,
            ),
        ),
        ids=ids,
        reappearance_seconds=3600,
    )

    assert {suppression.target_alarm_identity for suppression in decision.cascade_suppressions} == {
        identity('rule-a'),
        identity('rule-b'),
    }
    dispositions = _dispositions(decision)
    assert dispositions[identity('rule-a')].disposition is PriorityDisposition.CASCADE_SUPPRESSED
    assert dispositions[identity('rule-b')].disposition is PriorityDisposition.CASCADE_SUPPRESSED


def test_managed_non_predominant_special_condition_does_not_displace_higher_rule() -> None:
    plans = (
        plan('higher', kind=AlarmKind.IMPACT, priority_order=1),
        plan(
            'special',
            kind=AlarmKind.RISK,
            is_special_condition=True,
            priority_order=2,
        ),
        plan('lower', kind=AlarmKind.RISK, priority_order=3),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('higher', AlarmStatus.ACTIVE),
            physical('special', AlarmStatus.ACTIVE),
            physical('lower', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        plans,
        (
            physical('higher', AlarmStatus.ACTIVE, at=managed_at),
            physical('special', AlarmStatus.ACTIVE, at=managed_at),
            physical('lower', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'special',
                occurrence_id=_occurrence_id(started, 'special'),
                at=managed_at,
            ),
        ),
        ids=ids,
        reappearance_seconds=3600,
    )

    resolution = decision.priority_resolution
    assert resolution is not None
    assert resolution.predominant_alarm_identity == identity('higher')
    dispositions = _dispositions(decision)
    assert dispositions[identity('higher')].disposition is PriorityDisposition.PREDOMINANT
    assert dispositions[identity('lower')].disposition is PriorityDisposition.CASCADE_SUPPRESSED
    assert dispositions[identity('lower')].blocking_alarm_identities == (identity('special'),)


def test_managed_special_condition_becomes_predominant_when_higher_rule_normalizes() -> None:
    plans = (
        plan('higher', kind=AlarmKind.IMPACT, priority_order=1),
        plan(
            'special',
            kind=AlarmKind.RISK,
            is_special_condition=True,
            priority_order=2,
        ),
        plan('lower', kind=AlarmKind.RISK, priority_order=3),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('higher', AlarmStatus.ACTIVE),
            physical('special', AlarmStatus.ACTIVE),
            physical('lower', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('higher', AlarmStatus.ACTIVE, at=managed_at),
            physical('special', AlarmStatus.ACTIVE, at=managed_at),
            physical('lower', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'special',
                occurrence_id=_occurrence_id(started, 'special'),
                at=managed_at,
            ),
        ),
        ids=ids,
        reappearance_seconds=3600,
    )

    normalized_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('higher', AlarmStatus.INACTIVE, at=normalized_at),
            physical('special', AlarmStatus.ACTIVE, at=normalized_at),
            physical('lower', AlarmStatus.ACTIVE, at=normalized_at),
        ),
        at=normalized_at,
        ids=ids,
        reappearance_seconds=3600,
    )

    resolution = decision.priority_resolution
    assert resolution is not None
    assert resolution.predominant_alarm_identity == identity('special')
    dispositions = _dispositions(decision)
    assert dispositions[identity('special')].disposition is PriorityDisposition.PREDOMINANT
    assert dispositions[identity('lower')].disposition is PriorityDisposition.CASCADE_SUPPRESSED


def test_special_condition_returns_to_normal_priority_flow_when_management_effect_ends() -> None:
    plans = (
        plan(
            'special',
            kind=AlarmKind.RISK,
            is_special_condition=True,
            priority_order=1,
        ),
        plan('rule', kind=AlarmKind.IMPACT, priority_order=2),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('special', AlarmStatus.ACTIVE),
            physical('rule', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('special', AlarmStatus.ACTIVE, at=managed_at),
            physical('rule', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'special',
                occurrence_id=_occurrence_id(started, 'special'),
                at=managed_at,
            ),
        ),
        ids=ids,
        reappearance_seconds=300,
    )
    assert _dispositions(managed)[identity('rule')].disposition is (
        PriorityDisposition.CASCADE_SUPPRESSED
    )

    due = managed_at + timedelta(seconds=300)
    released = _reduce(
        managed.state,
        plans,
        (
            physical('special', AlarmStatus.ACTIVE, at=due),
            physical('rule', AlarmStatus.ACTIVE, at=due),
        ),
        at=due,
        ids=ids,
        reappearance_seconds=300,
    )

    assert released.cascade_suppressions == ()
    resolution = released.priority_resolution
    assert resolution is not None
    assert resolution.predominant_alarm_identity == identity('special')
    dispositions = _dispositions(released)
    assert dispositions[identity('special')].disposition is PriorityDisposition.PREDOMINANT
    assert dispositions[identity('rule')].disposition is PriorityDisposition.ECLIPSED
