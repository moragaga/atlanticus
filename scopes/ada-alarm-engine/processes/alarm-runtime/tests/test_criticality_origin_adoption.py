from dataclasses import replace
from datetime import timedelta

from ada.alarms.core import (
    AlarmRouting,
    AlarmStatus,
    DeactivationPolicy,
    PriorityDisposition,
    RoutingDestination,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import Criticality
from ada.processes.alarm_runtime import (
    AlarmOperationalInputs,
    AlarmPendingDeactivationRequest,
    ConfigurationAdoptionDisposition,
)

from .test_special_condition_flag_adoption import (
    AT,
    InputsProvider,
    _configuration,
    _cycle,
    _identity,
    _lifecycle,
    _session,
    _start_and_manage,
)


def _target(
    configuration: EngineAlarmConfiguration,
    *,
    release: str = 'ALARMS-8',
) -> EngineAlarmConfiguration:
    plans = tuple(
        replace(
            plan,
            alarm_configuration_revision=release,
            criticality=Criticality.C2,
            routing=AlarmRouting(
                origin_tool_key='tool_process',
                destinations=(RoutingDestination(tool_key='tool_future', delay_seconds=300),),
            ),
        )
        if plan.identity == _identity('alarm')
        else replace(plan, alarm_configuration_revision=release)
        for plan in configuration.planned_alarms
    )
    target_base = _configuration(
        release,
        is_special_condition=True,
        deactivation_enabled=(configuration.planned_alarms[0].deactivation_policy is not None),
        include_blocker=len(configuration.planned_alarms) > 1,
    )
    return EngineAlarmConfiguration(
        resolution_key=target_base.resolution_key,
        defined_alarm_identities=configuration.defined_alarm_identities,
        planned_alarms=plans,
        parameters_by_alarm=configuration.parameters_by_alarm,
    )


def test_criticality_origin_adoption_preserves_managed_cascade_and_reroutes() -> None:
    provider = InputsProvider()
    lifecycle = _lifecycle(provider)
    source = _configuration('ALARMS-7', is_special_condition=True, include_blocker=True)
    _source_session, managed, managed_at = _start_and_manage(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
        include_blocker=True,
    )
    before = managed.state.group_for('mill_feed')
    assert before is not None
    source_state = before.get(_identity('alarm'))
    blocker_state = before.get(_identity('blocker'))
    assert source_state is not None and source_state.occurrence is not None
    assert source_state.management_effect is not None
    assert blocker_state is not None and blocker_state.occurrence is not None

    target_session = _session(_target(source))
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {'alarm': AlarmStatus.ACTIVE, 'blocker': AlarmStatus.ACTIVE},
            at=managed_at + timedelta(seconds=5),
        ),
    )

    group = result.groups[0]
    assert result.adoption_plan is not None
    changes = {change.identity: change for change in result.adoption_plan.changes}
    assert changes[_identity('alarm')].disposition is ConfigurationAdoptionDisposition.COMPATIBLE
    assert group.adoption_decision is not None
    assert group.adoption_decision.occurrence_changes == ()
    assert group.adoption_decision.episode_changes == ()
    current = group.decision.state.get(_identity('alarm'))
    blocker = group.decision.state.get(_identity('blocker'))
    assert current is not None and current.occurrence is not None
    assert blocker is not None and blocker.occurrence is not None
    assert current.occurrence.occurrence_id == source_state.occurrence.occurrence_id
    assert current.management_effect == source_state.management_effect
    assert blocker.occurrence.occurrence_id == blocker_state.occurrence.occurrence_id
    assert group.decision.state.episode is not None
    assert before.episode is not None
    assert group.decision.state.episode.episode_id == before.episode.episode_id
    targets = {item.target_alarm_identity for item in group.decision.cascade_suppressions}
    assert targets == {_identity('blocker')}
    dispositions = {item.alarm_identity: item for item in group.decision.priority_resolution.alarms}
    assert dispositions[_identity('blocker')].disposition is PriorityDisposition.CASCADE_SUPPRESSED
    assert 'tool_process' in {assignment.tool_key for assignment in current.assignments}
    assert 'tool_a' not in {assignment.tool_key for assignment in current.assignments}
    assert {assignment.tool_key for assignment in current.pending_assignments} == {'tool_future'}


def test_criticality_origin_adoption_preserves_effective_deactivation() -> None:
    provider = InputsProvider()
    lifecycle = _lifecycle(provider)
    source = _configuration('ALARMS-7', is_special_condition=True, deactivation_enabled=True)
    _source_session, managed, managed_at = _start_and_manage(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
        deactivation_until=AT + timedelta(hours=1),
    )
    previous = managed.state.group_for('mill_feed')
    assert previous is not None
    before = previous.get(_identity('alarm'))
    assert before is not None and before.occurrence is not None
    assert before.deactivation_effect is not None
    target_session = _session(_target(source))
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {'alarm': AlarmStatus.ACTIVE},
            at=managed_at + timedelta(seconds=5),
        ),
    )
    group = result.groups[0]
    assert group.adoption_decision is not None
    assert group.adoption_decision.deactivation_effect_changes == ()
    current = group.decision.state.get(_identity('alarm'))
    assert current is not None and current.occurrence is not None
    assert current.occurrence.occurrence_id == before.occurrence.occurrence_id
    assert current.deactivation_effect == before.deactivation_effect


def test_pending_deactivation_request_remains_external_during_adoption() -> None:
    provider = InputsProvider()
    lifecycle = _lifecycle(provider)
    source_base = _configuration('ALARMS-7', is_special_condition=True, deactivation_enabled=True)
    source = EngineAlarmConfiguration(
        resolution_key=source_base.resolution_key,
        defined_alarm_identities=source_base.defined_alarm_identities,
        planned_alarms=(
            replace(
                source_base.planned_alarms[0],
                deactivation_policy=DeactivationPolicy(approval_required=True),
            ),
        ),
        parameters_by_alarm=source_base.parameters_by_alarm,
    )
    _session_before, managed, managed_at = _start_and_manage(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
        deactivation_until=AT + timedelta(hours=1),
    )
    previous = managed.state.group_for('mill_feed')
    assert previous is not None
    before = previous.get(_identity('alarm'))
    assert before is not None and before.occurrence is not None
    request = managed.groups[0].decision.deactivation_request_results[0].deactivation_request
    assert request is not None
    assert request.approval_required is True
    provider.value = AlarmOperationalInputs(
        pending_deactivation_requests=(
            AlarmPendingDeactivationRequest(request=request, priority_group='mill_feed'),
        ),
    )
    target_session = _session(_target(source))
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {'alarm': AlarmStatus.ACTIVE},
            at=managed_at + timedelta(seconds=5),
        ),
    )
    assert result.inputs.pending_deactivation_requests[0].request == request
    current = result.groups[0].decision.state.get(_identity('alarm'))
    assert current is not None and current.occurrence is not None
    assert current.occurrence.occurrence_id == before.occurrence.occurrence_id
    assert current.management_effect == before.management_effect
    assert current.deactivation_effect is None
    assert result.groups[0].decision.deactivation_effect_changes == ()
