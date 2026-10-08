from datetime import UTC, datetime, timedelta

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmResolutionKey,
    AlarmRouting,
    AlarmStatus,
    EvaluationContext,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    ManagementAction,
    PlannedAlarm,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality
from ada.processes.alarm_runtime import (
    AlarmEvaluationCycleResult,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    AlarmLifecycleCycle,
    AlarmOperationalInputs,
    ConfigurationAdoptionDisposition,
    build_alarm_execution_session,
)

AT = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)


class InputsProvider:
    def __init__(self) -> None:
        self.value = AlarmOperationalInputs()

    def read(self, *, session, cycle_at):
        return self.value


class Ids:
    def __init__(self) -> None:
        self.occurrences = 0
        self.episodes = 0
        self.management_effects = 0
        self.deactivation_requests = 0
        self.deactivation_effects = 0

    def occurrence(self, _identity, _at):
        self.occurrences += 1
        return f'O{self.occurrences}'

    def episode(self, _group, _at):
        self.episodes += 1
        return f'E{self.episodes}'

    def management_effect(self, _action):
        self.management_effects += 1
        return f'ME{self.management_effects}'

    def deactivation_request(self, _action):
        self.deactivation_requests += 1
        return f'DR{self.deactivation_requests}'

    def deactivation_effect(self, _request):
        self.deactivation_effects += 1
        return f'DE{self.deactivation_effects}'


def _identity(alarm_key: str) -> AlarmIdentity:
    return AlarmIdentity('mill', alarm_key)


def _plan(
    alarm_key: str,
    *,
    release: str,
    priority_order: int,
    is_special_condition: bool = False,
    reappearance_special_conditions: tuple[AlarmIdentity, ...] = (),
) -> PlannedAlarm:
    return PlannedAlarm(
        identity=_identity(alarm_key),
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        is_special_condition=is_special_condition,
        priority_group='mill_feed',
        priority_order=priority_order,
        evaluator_key='threshold',
        alarm_configuration_revision=release,
        tool_registry_revision='TOOLS-4',
        routing=AlarmRouting(origin_tool_key='tool_a'),
        reappearance_special_conditions=reappearance_special_conditions,
    )


def _configuration(
    release: str,
    *,
    reappearance_special_conditions: tuple[AlarmIdentity, ...] = (),
    include_blocker: bool = False,
) -> EngineAlarmConfiguration:
    plans = [
        _plan(
            'alarm',
            release=release,
            priority_order=1,
            reappearance_special_conditions=reappearance_special_conditions,
        ),
        _plan(
            'special',
            release=release,
            priority_order=2,
            is_special_condition=True,
        ),
    ]
    if include_blocker:
        plans.append(_plan('blocker', release=release, priority_order=3))
    planned = tuple(plans)
    identities = tuple(plan.identity for plan in planned)
    return EngineAlarmConfiguration(
        resolution_key=AlarmResolutionKey(release, 'TOOLS-4'),
        defined_alarm_identities=identities,
        planned_alarms=planned,
        parameters_by_alarm={identity: {} for identity in identities},
    )


def _evaluator(context: EvaluationContext) -> AlarmEvaluation:
    return AlarmEvaluation(
        alarm_identity=context.alarm_identity,
        status=AlarmStatus.INACTIVE,
        evaluated_at=context.now,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='test',
            contract_version='1',
            payload={},
        ),
    )


def _registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(
        contracts=(
            AlarmEvaluatorContract(
                family_key='mill',
                evaluator_key='threshold',
                evaluator=_evaluator,
            ),
        )
    )


def _session(configuration: EngineAlarmConfiguration):
    return build_alarm_execution_session(
        configuration=configuration,
        evaluator_registry=_registry(),
    )


def _evaluation(identity: AlarmIdentity, status: AlarmStatus, *, at: datetime) -> AlarmEvaluation:
    if status is AlarmStatus.ERROR:
        return AlarmEvaluation(
            alarm_identity=identity,
            status=status,
            evaluated_at=at,
            error=EvaluationError(
                origin=EvaluationErrorOrigin.QUALITY,
                error_key='insufficient_samples',
                message='Insufficient samples',
            ),
        )
    return AlarmEvaluation(
        alarm_identity=identity,
        status=status,
        evaluated_at=at,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='test',
            contract_version='1',
            payload={},
        ),
    )


def _cycle(
    session, statuses: dict[str, AlarmStatus], *, at: datetime
) -> AlarmEvaluationCycleResult:
    return AlarmEvaluationCycleResult(
        cycle_at=at,
        evaluations=tuple(
            _evaluation(
                entry.identity,
                statuses[entry.identity.alarm_key],
                at=at,
            )
            for entry in session.entries
        ),
    )


def _lifecycle(provider: InputsProvider):
    ids = Ids()
    return (
        AlarmLifecycleCycle(
            inputs_provider=provider,
            occurrence_id_factory=ids.occurrence,
            episode_id_factory=ids.episode,
            management_effect_id_factory=ids.management_effect,
            deactivation_request_id_factory=ids.deactivation_request,
            deactivation_effect_id_factory=ids.deactivation_effect,
        ),
        ids,
    )


def _manage_alarm(
    *,
    lifecycle: AlarmLifecycleCycle,
    provider: InputsProvider,
    configuration: EngineAlarmConfiguration,
    include_blocker: bool = False,
):
    session = _session(configuration)
    initial_statuses = {
        'alarm': AlarmStatus.ACTIVE,
        'special': AlarmStatus.INACTIVE,
    }
    if include_blocker:
        initial_statuses['blocker'] = AlarmStatus.ACTIVE

    started = lifecycle.run(
        previous=None,
        session=session,
        cycle=_cycle(session, initial_statuses, at=AT),
    )
    runtime = started.state.group_for('mill_feed').get(_identity('alarm'))
    assert runtime is not None
    assert runtime.occurrence is not None

    managed_at = AT + timedelta(seconds=5)
    provider.value = AlarmOperationalInputs(
        management_actions=(
            ManagementAction(
                input_id='management-1',
                alarm_identity=_identity('alarm'),
                source_occurrence_id=runtime.occurrence.occurrence_id,
                tool_key='tool_a',
                actor_key='operator',
                source_created_at=managed_at,
            ),
        )
    )
    managed = lifecycle.run(
        previous=started.state,
        session=session,
        cycle=_cycle(session, initial_statuses, at=managed_at),
    )
    provider.value = AlarmOperationalInputs()
    return session, managed, managed_at


def _adoption_change_for_alarm(result):
    assert result.adoption_plan is not None
    return next(
        change for change in result.adoption_plan.changes if change.identity == _identity('alarm')
    )


def test_added_active_special_condition_reappears_in_same_physical_cycle() -> None:
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    source = _configuration('ALARMS-7')
    _source_session, managed, managed_at = _manage_alarm(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
    )

    target = _configuration(
        'ALARMS-8',
        reappearance_special_conditions=(_identity('special'),),
    )
    target_session = _session(target)
    adoption_at = managed_at + timedelta(seconds=5)
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {
                'alarm': AlarmStatus.ACTIVE,
                'special': AlarmStatus.ACTIVE,
            },
            at=adoption_at,
        ),
    )

    assert _adoption_change_for_alarm(result).disposition is (
        ConfigurationAdoptionDisposition.COMPATIBLE
    )
    group = result.groups[0]
    assert group.adoption_decision is not None
    assert group.adoption_decision.reappearance_changes == ()
    runtime = group.decision.state.get(_identity('alarm'))
    assert runtime is not None
    assert runtime.occurrence is not None
    assert runtime.management_effect is None
    assert runtime.management_cycle == 2
    assert len(group.decision.reappearance_changes) == 1
    assert group.decision.reappearance_changes[0].effective_at == adoption_at


def test_added_inactive_special_condition_does_not_reappear() -> None:
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    source = _configuration('ALARMS-7')
    _source_session, managed, managed_at = _manage_alarm(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
    )

    target = _configuration(
        'ALARMS-8',
        reappearance_special_conditions=(_identity('special'),),
    )
    target_session = _session(target)
    adoption_at = managed_at + timedelta(seconds=5)
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {
                'alarm': AlarmStatus.ACTIVE,
                'special': AlarmStatus.INACTIVE,
            },
            at=adoption_at,
        ),
    )

    runtime = result.groups[0].decision.state.get(_identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is not None
    assert runtime.management_cycle == 1
    assert result.groups[0].decision.reappearance_changes == ()


def test_added_error_special_condition_does_not_reappear() -> None:
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    source = _configuration('ALARMS-7')
    _source_session, managed, managed_at = _manage_alarm(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
    )

    target = _configuration(
        'ALARMS-8',
        reappearance_special_conditions=(_identity('special'),),
    )
    target_session = _session(target)
    adoption_at = managed_at + timedelta(seconds=5)
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {
                'alarm': AlarmStatus.ACTIVE,
                'special': AlarmStatus.ERROR,
            },
            at=adoption_at,
        ),
    )

    runtime = result.groups[0].decision.state.get(_identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is not None
    assert runtime.management_cycle == 1
    assert result.groups[0].decision.reappearance_changes == ()


def test_removed_special_condition_no_longer_triggers_reappearance() -> None:
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    source = _configuration(
        'ALARMS-7',
        reappearance_special_conditions=(_identity('special'),),
    )
    _source_session, managed, managed_at = _manage_alarm(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
    )

    target = _configuration('ALARMS-8')
    target_session = _session(target)
    adoption_at = managed_at + timedelta(seconds=5)
    result = lifecycle.run(
        previous=managed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {
                'alarm': AlarmStatus.ACTIVE,
                'special': AlarmStatus.ACTIVE,
            },
            at=adoption_at,
        ),
    )

    assert _adoption_change_for_alarm(result).disposition is (
        ConfigurationAdoptionDisposition.COMPATIBLE
    )
    runtime = result.groups[0].decision.state.get(_identity('alarm'))
    assert runtime is not None
    assert runtime.management_effect is not None
    assert runtime.management_cycle == 1
    assert result.groups[0].decision.reappearance_changes == ()


def test_added_active_special_condition_does_not_resurrect_closed_occurrence() -> None:
    provider = InputsProvider()
    lifecycle, _ids = _lifecycle(provider)
    source = _configuration('ALARMS-7', include_blocker=True)
    source_session, managed, managed_at = _manage_alarm(
        lifecycle=lifecycle,
        provider=provider,
        configuration=source,
        include_blocker=True,
    )

    closed_at = managed_at + timedelta(seconds=5)
    closed = lifecycle.run(
        previous=managed.state,
        session=source_session,
        cycle=_cycle(
            source_session,
            {
                'alarm': AlarmStatus.INACTIVE,
                'special': AlarmStatus.INACTIVE,
                'blocker': AlarmStatus.ACTIVE,
            },
            at=closed_at,
        ),
    )
    closed_runtime = closed.state.group_for('mill_feed').get(_identity('alarm'))
    assert closed_runtime is not None
    assert closed_runtime.occurrence is None
    assert closed_runtime.management_effect is not None

    target = _configuration(
        'ALARMS-8',
        reappearance_special_conditions=(_identity('special'),),
        include_blocker=True,
    )
    target_session = _session(target)
    adoption_at = closed_at + timedelta(seconds=5)
    result = lifecycle.run(
        previous=closed.state,
        session=target_session,
        cycle=_cycle(
            target_session,
            {
                'alarm': AlarmStatus.INACTIVE,
                'special': AlarmStatus.ACTIVE,
                'blocker': AlarmStatus.ACTIVE,
            },
            at=adoption_at,
        ),
    )

    runtime = result.groups[0].decision.state.get(_identity('alarm'))
    assert runtime is not None
    assert runtime.occurrence is None
    assert runtime.management_effect is not None
    assert result.groups[0].decision.reappearance_changes == ()
