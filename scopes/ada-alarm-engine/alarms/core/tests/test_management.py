from dataclasses import replace
from datetime import timedelta

import pytest

from ada.alarms.core import (
    AlarmContractError,
    AlarmStatus,
    GroupLifecycleState,
    ManagementActionOutcome,
    ManagementEffectChangeKind,
    ReappearanceChange,
    is_directly_managed,
    reconcile_group_configuration,
    reduce_group_cycle,
)
from ada.contracts.alarms import AlarmKind

from .support import (
    NOW,
    Ids,
    error,
    identity,
    management_action,
    physical,
    plan,
)


def _reduce(
    state: GroupLifecycleState,
    plans,
    evaluations,
    *,
    at=NOW,
    actions=(),
    ids: Ids | None = None,
    reappearance_seconds: int | None = 300,
):
    generated = ids or Ids()

    def resolve_reappearance(action):
        if reappearance_seconds is None:
            return None
        return action.source_created_at + timedelta(seconds=reappearance_seconds)

    return reduce_group_cycle(
        state,
        cycle_at=at,
        planned_alarms=plans,
        evaluations=evaluations,
        management_actions=actions,
        occurrence_id_factory=generated.new_occurrence,
        episode_id_factory=generated.new_episode,
        management_effect_id_factory=generated.new_management_effect,
        reappearance_due_at_resolver=resolve_reappearance,
    )


def _start_risk(ids: Ids | None = None):
    generated = ids or Ids()
    decision = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE)],
        ids=generated,
    )
    return decision, generated


def _start_impact_and_risk(ids: Ids | None = None):
    generated = ids or Ids()
    plans = [
        plan(
            'impact',
            kind=AlarmKind.IMPACT,
            priority_order=1,
        ),
        plan('risk', kind=AlarmKind.RISK, priority_order=2),
    ]
    decision = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE),
            physical('risk', AlarmStatus.ACTIVE),
        ],
        ids=generated,
    )
    return decision, generated, plans


def _manage_impact(started, ids, plans, *, at):
    return _reduce(
        started.state,
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE, at=at),
            physical('risk', AlarmStatus.ACTIVE, at=at),
        ],
        at=at,
        actions=(management_action('impact', occurrence_id='O1', at=at),),
        ids=ids,
    )


def test_first_management_is_effective_and_starts_reappearance_clock() -> None:
    started, ids = _start_risk()
    at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=at)],
        at=at,
        actions=(management_action('risk', at=at),),
        ids=ids,
    )
    result = decision.management_action_results[0]
    assert result.outcome is ManagementActionOutcome.EFFECTIVE
    assert result.management_cycle == 1
    assert result.management_effect_id == 'ME1'
    runtime = decision.state.get(identity('risk'))
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_effect.reappearance_due_at == at + timedelta(seconds=300)
    assert is_directly_managed(runtime, at=at)


def test_additional_management_does_not_replace_effect_or_restart_timer() -> None:
    started, ids = _start_risk()
    first_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=first_at)],
        at=first_at,
        actions=(management_action('risk', input_id='M1', at=first_at),),
        ids=ids,
    )
    original = managed.state.get(identity('risk'))
    assert original is not None and original.management_effect is not None
    second_at = first_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=second_at)],
        at=second_at,
        actions=(management_action('risk', input_id='M2', at=second_at),),
        ids=ids,
    )
    result = decision.management_action_results[0]
    assert result.outcome is ManagementActionOutcome.ADDITIONAL
    runtime = decision.state.get(identity('risk'))
    assert runtime is not None
    assert runtime.management_effect == original.management_effect
    assert decision.management_effect_changes == ()


def test_same_time_management_uses_stable_input_id_for_effective_action() -> None:
    started, ids = _start_risk()
    at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=at)],
        at=at,
        actions=(
            management_action('risk', input_id='M2', at=at),
            management_action('risk', input_id='M1', at=at),
        ),
        ids=ids,
    )
    results = decision.management_action_results
    assert [item.action.input_id for item in results] == ['M1', 'M2']
    assert [item.outcome for item in results] == [
        ManagementActionOutcome.EFFECTIVE,
        ManagementActionOutcome.ADDITIONAL,
    ]


def test_reappearance_keeps_occurrence_and_increments_management_cycle() -> None:
    started, ids = _start_risk()
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=managed_at)],
        at=managed_at,
        actions=(management_action('risk', at=managed_at),),
        ids=ids,
    )
    due = managed_at + timedelta(seconds=300)
    decision = _reduce(
        managed.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=due)],
        at=due,
        ids=ids,
    )
    runtime = decision.state.get(identity('risk'))
    assert runtime is not None and runtime.occurrence is not None
    assert runtime.occurrence.occurrence_id == 'O1'
    assert runtime.management_cycle == 2
    assert runtime.management_effect is None
    assert decision.reappearance_changes == (
        ReappearanceChange(
            alarm_identity=identity('risk'),
            occurrence_id='O1',
            effective_at=due,
            management_cycle=2,
        ),
    )


def test_management_at_exact_reappearance_deadline_wins_without_artificial_reappearance() -> None:
    started, ids = _start_risk()
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=managed_at)],
        at=managed_at,
        actions=(management_action('risk', input_id='M1', at=managed_at),),
        ids=ids,
    )
    due = managed_at + timedelta(seconds=300)
    decision = _reduce(
        managed.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=due)],
        at=due,
        actions=(management_action('risk', input_id='M2', at=due),),
        ids=ids,
    )
    runtime = decision.state.get(identity('risk'))
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_cycle == 2
    assert runtime.management_effect.effect_id == 'ME2'
    assert decision.reappearance_changes == ()
    assert decision.management_action_results[0].outcome is ManagementActionOutcome.EFFECTIVE


def test_management_and_normalization_same_time_records_management_then_closes() -> None:
    started, ids = _start_risk()
    at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.INACTIVE, at=at)],
        at=at,
        actions=(management_action('risk', at=at),),
        ids=ids,
    )
    assert decision.management_action_results[0].outcome is ManagementActionOutcome.EFFECTIVE
    assert decision.state.episode is None
    assert decision.state.alarms == ()
    assert decision.reappearance_changes == ()
    assert {change.kind for change in decision.management_effect_changes} == {
        ManagementEffectChangeKind.STARTED,
        ManagementEffectChangeKind.CLEARED,
    }


def test_reappearance_and_normalization_same_time_prefers_normalization() -> None:
    started, ids = _start_risk()
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=managed_at)],
        at=managed_at,
        actions=(management_action('risk', at=managed_at),),
        ids=ids,
    )
    due = managed_at + timedelta(seconds=300)
    decision = _reduce(
        managed.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.INACTIVE, at=due)],
        at=due,
        ids=ids,
    )
    assert decision.reappearance_changes == ()
    assert decision.state.episode is None
    assert decision.state.alarms == ()


def test_management_during_technical_hold_coexists_with_hold() -> None:
    started, ids = _start_risk()
    error_at = NOW + timedelta(seconds=10)
    held = _reduce(
        started.state,
        [plan('risk')],
        [error('risk', at=error_at)],
        at=error_at,
        ids=ids,
    )
    managed_at = error_at + timedelta(seconds=10)
    decision = _reduce(
        held.state,
        [plan('risk')],
        [error('risk', at=managed_at)],
        at=managed_at,
        actions=(management_action('risk', at=managed_at),),
        ids=ids,
    )
    runtime = decision.state.get(identity('risk'))
    assert runtime is not None
    assert runtime.technical_hold is not None
    assert runtime.management_effect is not None
    assert decision.management_action_results[0].outcome is ManagementActionOutcome.EFFECTIVE


def test_managed_impact_cascades_to_lower_active_risk() -> None:
    started, ids, plans = _start_impact_and_risk()
    at = NOW + timedelta(minutes=1)
    decision = _manage_impact(started, ids, plans, at=at)
    assert len(decision.cascade_suppressions) == 1
    suppression = decision.cascade_suppressions[0]
    assert suppression.source_alarm_identity == identity('impact')
    assert suppression.target_alarm_identity == identity('risk')


def test_lower_rank_risk_management_does_not_suppress_higher_rank_impact() -> None:
    started, ids, plans = _start_impact_and_risk()
    at = NOW + timedelta(minutes=1)
    decision = _reduce(
        started.state,
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE, at=at),
            physical('risk', AlarmStatus.ACTIVE, at=at),
        ],
        at=at,
        actions=(management_action('risk', occurrence_id='O2', at=at),),
        ids=ids,
    )
    assert decision.management_action_results[0].outcome is ManagementActionOutcome.EFFECTIVE
    assert decision.cascade_suppressions == ()


def test_impact_effect_survives_source_close_while_lower_risk_remains_active() -> None:
    started, ids, plans = _start_impact_and_risk()
    managed_at = NOW + timedelta(minutes=1)
    managed = _manage_impact(started, ids, plans, at=managed_at)
    closed_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=closed_at),
            physical('risk', AlarmStatus.ACTIVE, at=closed_at),
        ],
        at=closed_at,
        ids=ids,
    )
    impact = decision.state.get(identity('impact'))
    assert impact is not None
    assert impact.occurrence is None
    assert impact.management_effect is not None
    assert len(decision.cascade_suppressions) == 1


def test_new_impact_occurrence_does_not_inherit_direct_old_management() -> None:
    started, ids, plans = _start_impact_and_risk()
    managed_at = NOW + timedelta(minutes=1)
    managed = _manage_impact(started, ids, plans, at=managed_at)
    closed_at = managed_at + timedelta(minutes=1)
    impact_closed = _reduce(
        managed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=closed_at),
            physical('risk', AlarmStatus.ACTIVE, at=closed_at),
        ],
        at=closed_at,
        ids=ids,
    )
    reopened_at = closed_at + timedelta(minutes=1)
    decision = _reduce(
        impact_closed.state,
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE, at=reopened_at),
            physical('risk', AlarmStatus.ACTIVE, at=reopened_at),
        ],
        at=reopened_at,
        ids=ids,
    )
    impact = decision.state.get(identity('impact'))
    assert impact is not None and impact.occurrence is not None
    assert impact.occurrence.occurrence_id != 'O1'
    assert impact.management_effect is not None
    assert impact.management_effect.source_occurrence_id == 'O1'
    assert not is_directly_managed(impact, at=reopened_at)
    assert len(decision.cascade_suppressions) == 1


def test_late_impact_management_can_create_cascade_with_same_episode_risk() -> None:
    started, ids, plans = _start_impact_and_risk()
    close_at = NOW + timedelta(minutes=1)
    impact_closed = _reduce(
        started.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=close_at),
            physical('risk', AlarmStatus.ACTIVE, at=close_at),
        ],
        at=close_at,
        ids=ids,
    )
    action_at = close_at + timedelta(seconds=30)
    cycle_at = close_at + timedelta(minutes=1)
    decision = _reduce(
        impact_closed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=cycle_at),
            physical('risk', AlarmStatus.ACTIVE, at=cycle_at),
        ],
        at=cycle_at,
        actions=(management_action('impact', occurrence_id='O1', at=action_at),),
        ids=ids,
    )
    result = decision.management_action_results[0]
    assert result.outcome is ManagementActionOutcome.LATE
    assert result.management_effect_id == 'ME1'
    assert len(decision.cascade_suppressions) == 1
    assert decision.cascade_suppressions[0].target_alarm_identity == identity('risk')


def test_late_management_after_episode_closed_has_no_operational_effect() -> None:
    started, ids, plans = _start_impact_and_risk()
    close_at = NOW + timedelta(minutes=1)
    closed = _reduce(
        started.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=close_at),
            physical('risk', AlarmStatus.INACTIVE, at=close_at),
        ],
        at=close_at,
        ids=ids,
    )
    cycle_at = close_at + timedelta(minutes=1)
    decision = _reduce(
        closed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=cycle_at),
            physical('risk', AlarmStatus.INACTIVE, at=cycle_at),
        ],
        at=cycle_at,
        actions=(
            management_action(
                'impact',
                occurrence_id='O1',
                at=close_at + timedelta(seconds=30),
            ),
        ),
        ids=ids,
    )
    result = decision.management_action_results[0]
    assert result.outcome is ManagementActionOutcome.LATE
    assert result.management_effect_id is None
    assert decision.cascade_suppressions == ()
    assert decision.state.alarms == ()


def test_management_for_old_occurrence_never_transfers_to_new_occurrence() -> None:
    ids = Ids()
    started, _, plans = _start_impact_and_risk(ids)
    close_at = NOW + timedelta(minutes=1)
    closed = _reduce(
        started.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=close_at),
            physical('risk', AlarmStatus.INACTIVE, at=close_at),
        ],
        at=close_at,
        ids=ids,
    )
    reopen_at = close_at + timedelta(minutes=1)
    reopened = _reduce(
        closed.state,
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE, at=reopen_at),
            physical('risk', AlarmStatus.ACTIVE, at=reopen_at),
        ],
        at=reopen_at,
        ids=ids,
    )
    cycle_at = reopen_at + timedelta(minutes=1)
    decision = _reduce(
        reopened.state,
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE, at=cycle_at),
            physical('risk', AlarmStatus.ACTIVE, at=cycle_at),
        ],
        at=cycle_at,
        actions=(
            management_action(
                'impact',
                occurrence_id='O1',
                at=reopen_at + timedelta(seconds=30),
            ),
        ),
        ids=ids,
    )
    result = decision.management_action_results[0]
    assert result.outcome is ManagementActionOutcome.LATE
    impact = decision.state.get(identity('impact'))
    assert impact is not None and impact.occurrence is not None
    assert impact.management_effect is None


def test_management_only_effect_expiry_releases_cascade_without_reappearance() -> None:
    started, ids, plans = _start_impact_and_risk()
    managed_at = NOW + timedelta(minutes=1)
    managed = _manage_impact(started, ids, plans, at=managed_at)
    close_at = managed_at + timedelta(minutes=1)
    impact_closed = _reduce(
        managed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=close_at),
            physical('risk', AlarmStatus.ACTIVE, at=close_at),
        ],
        at=close_at,
        ids=ids,
    )
    due = managed_at + timedelta(seconds=300)
    decision = _reduce(
        impact_closed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=due),
            physical('risk', AlarmStatus.ACTIVE, at=due),
        ],
        at=due,
        ids=ids,
    )
    assert decision.state.get(identity('impact')) is None
    assert decision.reappearance_changes == ()
    assert decision.cascade_suppressions == ()


def test_compatible_reconfiguration_preserves_management_only_effect_and_cascade() -> None:
    started, ids, plans = _start_impact_and_risk()
    plans[0] = replace(plans[0], reappearance_after_seconds=300)
    managed_at = NOW + timedelta(minutes=1)
    managed = _manage_impact(started, ids, plans, at=managed_at)
    close_at = managed_at + timedelta(minutes=1)
    impact_closed = _reduce(
        managed.state,
        plans,
        [
            physical('impact', AlarmStatus.INACTIVE, at=close_at),
            physical('risk', AlarmStatus.ACTIVE, at=close_at),
        ],
        at=close_at,
        ids=ids,
    )
    previous_impact = impact_closed.state.get(identity('impact'))
    previous_risk = impact_closed.state.get(identity('risk'))
    assert previous_impact is not None and previous_impact.occurrence is None
    assert previous_impact.management_effect is not None
    assert previous_risk is not None and previous_risk.occurrence is not None

    changed_plan = replace(
        plans[0],
        routing=replace(plans[0].routing, origin_tool_key='tool-c'),
    )
    adopted_at = close_at + timedelta(seconds=10)
    decision = reconcile_group_configuration(
        impact_closed.state,
        effective_at=adopted_at,
        planned_alarms=(changed_plan, plans[1]),
    )

    impact = decision.state.get(identity('impact'))
    risk = decision.state.get(identity('risk'))
    assert impact is not None and impact.occurrence is None
    assert impact.management_effect == previous_impact.management_effect
    assert risk is not None and risk.occurrence == previous_risk.occurrence
    assert decision.state.episode == impact_closed.state.episode
    assert decision.occurrence_changes == ()
    assert decision.episode_changes == ()
    assert decision.management_effect_changes == ()
    assert {item.target_alarm_identity for item in decision.cascade_suppressions} == {
        identity('risk')
    }


def test_duplicate_management_input_id_is_rejected() -> None:
    started, ids = _start_risk()
    at = NOW + timedelta(minutes=1)
    with pytest.raises(AlarmContractError, match='duplicate input_id'):
        _reduce(
            started.state,
            [plan('risk')],
            [physical('risk', AlarmStatus.ACTIVE, at=at)],
            at=at,
            actions=(
                management_action('risk', input_id='M1', at=at),
                management_action('risk', input_id='M1', at=at),
            ),
            ids=ids,
        )


def test_future_management_action_is_rejected() -> None:
    started, ids = _start_risk()
    at = NOW + timedelta(minutes=1)
    with pytest.raises(AlarmContractError, match='must not be after cycle_at'):
        _reduce(
            started.state,
            [plan('risk')],
            [physical('risk', AlarmStatus.ACTIVE, at=at)],
            at=at,
            actions=(management_action('risk', at=at + timedelta(seconds=1)),),
            ids=ids,
        )


def test_managed_impact_effect_survives_overdue_technical_hold_when_risk_keeps_episode_open() -> (
    None
):
    started, ids, plans = _start_impact_and_risk()
    managed_at = NOW + timedelta(seconds=10)
    managed = _reduce(
        started.state,
        plans,
        [
            physical('impact', AlarmStatus.ACTIVE, at=managed_at),
            physical('risk', AlarmStatus.ACTIVE, at=managed_at),
        ],
        at=managed_at,
        actions=(management_action('impact', occurrence_id='O1', at=managed_at),),
        ids=ids,
        reappearance_seconds=1000,
    )
    error_at = managed_at + timedelta(seconds=10)
    held = _reduce(
        managed.state,
        plans,
        [error('impact', at=error_at), physical('risk', AlarmStatus.ACTIVE, at=error_at)],
        at=error_at,
        ids=ids,
        reappearance_seconds=1000,
    )
    recovery_at = error_at + timedelta(seconds=400)
    decision = _reduce(
        held.state,
        plans,
        [error('impact', at=recovery_at), physical('risk', AlarmStatus.ACTIVE, at=recovery_at)],
        at=recovery_at,
        ids=ids,
        reappearance_seconds=1000,
    )
    impact = decision.state.get(identity('impact'))
    assert impact is not None
    assert impact.occurrence is None
    assert impact.management_effect is not None
    assert len(decision.cascade_suppressions) == 1


def test_episode_end_by_overdue_technical_hold_clears_management_effect_at_due_time() -> None:
    started, ids = _start_risk()
    managed_at = NOW + timedelta(seconds=10)
    managed = _reduce(
        started.state,
        [plan('risk')],
        [physical('risk', AlarmStatus.ACTIVE, at=managed_at)],
        at=managed_at,
        actions=(management_action('risk', at=managed_at),),
        ids=ids,
        reappearance_seconds=1000,
    )
    error_at = managed_at + timedelta(seconds=10)
    held = _reduce(
        managed.state,
        [plan('risk')],
        [error('risk', at=error_at)],
        at=error_at,
        ids=ids,
        reappearance_seconds=1000,
    )
    technical_due = error_at + timedelta(seconds=300)
    recovery_at = technical_due + timedelta(seconds=10)
    decision = _reduce(
        held.state,
        [plan('risk')],
        [error('risk', at=recovery_at)],
        at=recovery_at,
        ids=ids,
        reappearance_seconds=1000,
    )
    assert decision.state.episode is None
    assert decision.state.alarms == ()
    cleared = [
        change
        for change in decision.management_effect_changes
        if change.kind is ManagementEffectChangeKind.CLEARED
    ]
    assert len(cleared) == 1
    assert cleared[0].effective_at == technical_due


def _managed_risk_with_reappearance(seconds: int | None):
    ids = Ids()
    alarm = plan('risk', reappearance_after_seconds=seconds)
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        (alarm,),
        (physical('risk', AlarmStatus.ACTIVE),),
        ids=ids,
        reappearance_seconds=seconds,
    )
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        (alarm,),
        (physical('risk', AlarmStatus.ACTIVE, at=managed_at),),
        at=managed_at,
        actions=(management_action('risk', at=managed_at),),
        ids=ids,
        reappearance_seconds=seconds,
    )
    return alarm, managed, ids, managed_at


def test_management_without_timer_remains_managed_while_condition_stays_active() -> None:
    alarm, managed, ids, managed_at = _managed_risk_with_reappearance(None)
    later = managed_at + timedelta(hours=1)
    decision = _reduce(
        managed.state,
        (alarm,),
        (physical('risk', AlarmStatus.ACTIVE, at=later),),
        at=later,
        ids=ids,
        reappearance_seconds=None,
    )

    runtime = decision.state.get(alarm.identity)
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_effect.reappearance_due_at is None
    assert is_directly_managed(runtime, at=later)
    assert decision.reappearance_changes == ()


def test_special_condition_only_reappearance_works_without_timer() -> None:
    risk = plan(
        'risk',
        priority_order=1,
        reappearance_after_seconds=None,
        reappearance_special_conditions=(identity('special'),),
    )
    special = plan(
        'special',
        priority_order=2,
        reappearance_after_seconds=None,
    )
    plans = (risk, special)
    ids = Ids()
    started = _reduce(
        GroupLifecycleState(priority_group='mill-feed'),
        plans,
        (
            physical('risk', AlarmStatus.ACTIVE),
            physical('special', AlarmStatus.INACTIVE),
        ),
        ids=ids,
        reappearance_seconds=None,
    )
    managed_at = NOW + timedelta(minutes=1)
    managed = _reduce(
        started.state,
        plans,
        (
            physical('risk', AlarmStatus.ACTIVE, at=managed_at),
            physical('special', AlarmStatus.INACTIVE, at=managed_at),
        ),
        at=managed_at,
        actions=(management_action('risk', at=managed_at),),
        ids=ids,
        reappearance_seconds=None,
    )
    trigger_at = managed_at + timedelta(minutes=1)
    decision = _reduce(
        managed.state,
        plans,
        (
            physical('risk', AlarmStatus.ACTIVE, at=trigger_at),
            physical('special', AlarmStatus.ACTIVE, at=trigger_at),
        ),
        at=trigger_at,
        ids=ids,
        reappearance_seconds=None,
    )

    runtime = decision.state.get(risk.identity)
    assert runtime is not None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert decision.reappearance_changes == (
        ReappearanceChange(
            alarm_identity=risk.identity,
            occurrence_id='O1',
            effective_at=trigger_at,
            management_cycle=2,
        ),
    )


def test_reappearance_delay_300_to_600_recalculates_from_original_effective_at() -> None:
    source, managed, _ids, managed_at = _managed_risk_with_reappearance(300)
    target = replace(source, reappearance_after_seconds=600)
    adoption_at = managed_at + timedelta(seconds=400)

    decision = reconcile_group_configuration(
        managed.state,
        effective_at=adoption_at,
        planned_alarms=(target,),
    )

    runtime = decision.state.get(source.identity)
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_effect.reappearance_due_at == managed_at + timedelta(seconds=600)
    assert decision.reappearance_changes == ()
    assert len(decision.management_effect_changes) == 1
    change = decision.management_effect_changes[0]
    assert change.kind is ManagementEffectChangeKind.UPDATED
    assert change.effective_at == adoption_at
    assert change.management_effect == runtime.management_effect


def test_reappearance_delay_300_to_none_removes_temporal_deadline() -> None:
    source, managed, _ids, managed_at = _managed_risk_with_reappearance(300)
    target = replace(source, reappearance_after_seconds=None)
    adoption_at = managed_at + timedelta(seconds=30)

    decision = reconcile_group_configuration(
        managed.state,
        effective_at=adoption_at,
        planned_alarms=(target,),
    )

    runtime = decision.state.get(source.identity)
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_effect.reappearance_due_at is None
    assert decision.management_effect_changes[0].kind is ManagementEffectChangeKind.UPDATED


def test_reappearance_delay_none_to_60_creates_temporal_deadline() -> None:
    source, managed, _ids, managed_at = _managed_risk_with_reappearance(None)
    target = replace(source, reappearance_after_seconds=60)
    adoption_at = managed_at + timedelta(seconds=30)

    decision = reconcile_group_configuration(
        managed.state,
        effective_at=adoption_at,
        planned_alarms=(target,),
    )

    runtime = decision.state.get(source.identity)
    assert runtime is not None and runtime.management_effect is not None
    assert runtime.management_effect.reappearance_due_at == managed_at + timedelta(seconds=60)
    assert decision.management_effect_changes[0].kind is ManagementEffectChangeKind.UPDATED


def test_overdue_reconciled_deadline_active_reappears_in_same_physical_cycle() -> None:
    source, managed, ids, managed_at = _managed_risk_with_reappearance(None)
    target = replace(source, reappearance_after_seconds=60)
    cycle_at = managed_at + timedelta(seconds=120)

    adoption = reconcile_group_configuration(
        managed.state,
        effective_at=cycle_at,
        planned_alarms=(target,),
    )
    adopted_runtime = adoption.state.get(source.identity)
    assert adopted_runtime is not None and adopted_runtime.management_effect is not None
    assert adopted_runtime.management_effect.reappearance_due_at == cycle_at
    assert adoption.reappearance_changes == ()

    decision = _reduce(
        adoption.state,
        (target,),
        (physical('risk', AlarmStatus.ACTIVE, at=cycle_at),),
        at=cycle_at,
        ids=ids,
        reappearance_seconds=60,
    )

    runtime = decision.state.get(source.identity)
    assert runtime is not None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert decision.reappearance_changes == (
        ReappearanceChange(
            alarm_identity=source.identity,
            occurrence_id='O1',
            effective_at=cycle_at,
            management_cycle=2,
        ),
    )


def test_overdue_reconciled_deadline_inactive_normalizes_without_reappearance() -> None:
    source, managed, ids, managed_at = _managed_risk_with_reappearance(None)
    target = replace(source, reappearance_after_seconds=60)
    cycle_at = managed_at + timedelta(seconds=120)

    adoption = reconcile_group_configuration(
        managed.state,
        effective_at=cycle_at,
        planned_alarms=(target,),
    )

    decision = _reduce(
        adoption.state,
        (target,),
        (physical('risk', AlarmStatus.INACTIVE, at=cycle_at),),
        at=cycle_at,
        ids=ids,
        reappearance_seconds=60,
    )

    assert decision.reappearance_changes == ()
    assert decision.state.episode is None
    assert decision.state.alarms == ()
