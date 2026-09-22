from datetime import timedelta

from ada_command_center.alarms.core import (
    AlarmStatus,
    GroupLifecycleState,
    PriorityDisposition,
    ToolAssignment,
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


def test_higher_rank_emerges_above_managed_lower_rank_and_lower_barrier_remains() -> None:
    plans = (
        plan('impact-a', kind=AlarmKind.IMPACT, priority_order=1),
        plan('impact-b', kind=AlarmKind.IMPACT, priority_order=2),
        plan('risk', kind=AlarmKind.RISK, priority_order=3),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('impact-a', AlarmStatus.INACTIVE),
            physical('impact-b', AlarmStatus.ACTIVE),
            physical('risk', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('impact-a', AlarmStatus.INACTIVE, at=managed_at),
            physical('impact-b', AlarmStatus.ACTIVE, at=managed_at),
            physical('risk', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'impact-b',
                occurrence_id=_occurrence_id(started, 'impact-b'),
                at=managed_at,
            ),
        ),
        ids=ids,
    )

    emerged_at = managed_at + timedelta(minutes=1)
    emerged = _reduce(
        managed.state,
        plans,
        (
            physical('impact-a', AlarmStatus.ACTIVE, at=emerged_at),
            physical('impact-b', AlarmStatus.ACTIVE, at=emerged_at),
            physical('risk', AlarmStatus.ACTIVE, at=emerged_at),
        ),
        at=emerged_at,
        ids=ids,
    )

    resolution = emerged.priority_resolution
    assert resolution is not None
    assert resolution.predominant_alarm_identity == identity('impact-a')
    assert {suppression.target_alarm_identity for suppression in emerged.cascade_suppressions} == {
        identity('risk')
    }

    dispositions = _dispositions(emerged)
    assert dispositions[identity('impact-a')].disposition is PriorityDisposition.PREDOMINANT
    assert dispositions[identity('risk')].disposition is PriorityDisposition.CASCADE_SUPPRESSED
    assert dispositions[identity('risk')].blocking_alarm_identities == (identity('impact-b'),)

    normalized_at = emerged_at + timedelta(minutes=1)
    normalized = _reduce(
        emerged.state,
        plans,
        (
            physical('impact-a', AlarmStatus.INACTIVE, at=normalized_at),
            physical('impact-b', AlarmStatus.ACTIVE, at=normalized_at),
            physical('risk', AlarmStatus.ACTIVE, at=normalized_at),
        ),
        at=normalized_at,
        ids=ids,
    )

    managed_runtime = normalized.state.get(identity('impact-b'))
    assert managed_runtime is not None
    assert managed_runtime.management_effect is not None
    dispositions = _dispositions(normalized)
    assert dispositions[identity('risk')].disposition is PriorityDisposition.CASCADE_SUPPRESSED
    assert dispositions[identity('risk')].blocking_alarm_identities == (identity('impact-b'),)


def test_cascade_suppression_does_not_stop_c2_routing() -> None:
    plans = (
        plan('impact', kind=AlarmKind.IMPACT, priority_order=1),
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
            ),
        ),
        ids=ids,
        reappearance_seconds=3600,
    )

    due = NOW + timedelta(minutes=15)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('impact', AlarmStatus.ACTIVE, at=due),
            physical('risk', AlarmStatus.ACTIVE, at=due),
        ),
        at=due,
        ids=ids,
    )

    risk = decision.state.get(identity('risk'))
    assert risk is not None
    assert ToolAssignment('tool-b', due) in risk.assignments
    dispositions = _dispositions(decision)
    assert dispositions[identity('risk')].disposition is PriorityDisposition.CASCADE_SUPPRESSED


def test_management_effect_expiry_releases_suppression_and_recomputes_priority() -> None:
    plans = (
        plan('impact', kind=AlarmKind.IMPACT, priority_order=1),
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
            ),
        ),
        ids=ids,
    )

    closed_at = managed_at + timedelta(minutes=1)
    closed = _reduce(
        managed.state,
        plans,
        (
            physical('impact', AlarmStatus.INACTIVE, at=closed_at),
            physical('risk', AlarmStatus.ACTIVE, at=closed_at),
        ),
        at=closed_at,
        ids=ids,
    )

    impact = closed.state.get(identity('impact'))
    assert impact is not None
    assert impact.occurrence is None
    assert impact.management_effect is not None
    assert _dispositions(closed)[identity('risk')].disposition is (
        PriorityDisposition.CASCADE_SUPPRESSED
    )

    due = managed_at + timedelta(seconds=300)
    released = _reduce(
        closed.state,
        plans,
        (
            physical('impact', AlarmStatus.INACTIVE, at=due),
            physical('risk', AlarmStatus.ACTIVE, at=due),
        ),
        at=due,
        ids=ids,
    )

    assert released.cascade_suppressions == ()
    assert released.state.get(identity('impact')) is None
    resolution = released.priority_resolution
    assert resolution is not None
    assert resolution.predominant_alarm_identity == identity('risk')
    assert _dispositions(released)[identity('risk')].disposition is (
        PriorityDisposition.PREDOMINANT
    )


def test_managed_higher_rank_impact_suppresses_lower_rank_impact() -> None:
    plans = (
        plan('impact-a', kind=AlarmKind.IMPACT, priority_order=1),
        plan('impact-b', kind=AlarmKind.IMPACT, priority_order=2),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('impact-a', AlarmStatus.ACTIVE),
            physical('impact-b', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        plans,
        (
            physical('impact-a', AlarmStatus.ACTIVE, at=managed_at),
            physical('impact-b', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'impact-a',
                occurrence_id=_occurrence_id(started, 'impact-a'),
                at=managed_at,
            ),
        ),
        ids=ids,
    )

    assert {
        (
            suppression.source_alarm_identity,
            suppression.target_alarm_identity,
        )
        for suppression in decision.cascade_suppressions
    } == {(identity('impact-a'), identity('impact-b'))}
    dispositions = _dispositions(decision)
    assert dispositions[identity('impact-b')].disposition is (
        PriorityDisposition.CASCADE_SUPPRESSED
    )
    assert dispositions[identity('impact-b')].blocking_alarm_identities == (identity('impact-a'),)


def test_managed_higher_rank_risk_suppresses_lower_rank_risk() -> None:
    plans = (
        plan('risk-a', kind=AlarmKind.RISK, priority_order=1),
        plan('risk-b', kind=AlarmKind.RISK, priority_order=2),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('risk-a', AlarmStatus.ACTIVE),
            physical('risk-b', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        plans,
        (
            physical('risk-a', AlarmStatus.ACTIVE, at=managed_at),
            physical('risk-b', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'risk-a',
                occurrence_id=_occurrence_id(started, 'risk-a'),
                at=managed_at,
            ),
        ),
        ids=ids,
    )

    assert {
        (
            suppression.source_alarm_identity,
            suppression.target_alarm_identity,
        )
        for suppression in decision.cascade_suppressions
    } == {(identity('risk-a'), identity('risk-b'))}
    dispositions = _dispositions(decision)
    assert dispositions[identity('risk-b')].disposition is (PriorityDisposition.CASCADE_SUPPRESSED)
    assert dispositions[identity('risk-b')].blocking_alarm_identities == (identity('risk-a'),)


def test_management_effect_survives_source_close_for_lower_same_kind_alarm() -> None:
    plans = (
        plan('impact-a', kind=AlarmKind.IMPACT, priority_order=1),
        plan('impact-b', kind=AlarmKind.IMPACT, priority_order=2),
    )
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('impact-a', AlarmStatus.ACTIVE),
            physical('impact-b', AlarmStatus.ACTIVE),
        ),
        ids=ids,
    )

    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('impact-a', AlarmStatus.ACTIVE, at=managed_at),
            physical('impact-b', AlarmStatus.ACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(
            management_action(
                'impact-a',
                occurrence_id=_occurrence_id(started, 'impact-a'),
                at=managed_at,
            ),
        ),
        ids=ids,
    )

    closed_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('impact-a', AlarmStatus.INACTIVE, at=closed_at),
            physical('impact-b', AlarmStatus.ACTIVE, at=closed_at),
        ),
        at=closed_at,
        ids=ids,
    )

    source = decision.state.get(identity('impact-a'))
    assert source is not None
    assert source.occurrence is None
    assert source.management_effect is not None
    assert {
        (
            suppression.source_alarm_identity,
            suppression.target_alarm_identity,
        )
        for suppression in decision.cascade_suppressions
    } == {(identity('impact-a'), identity('impact-b'))}
    dispositions = _dispositions(decision)
    assert dispositions[identity('impact-b')].disposition is (
        PriorityDisposition.CASCADE_SUPPRESSED
    )
