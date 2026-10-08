# Espejo pedagógico de la orquestación lifecycle posterior a la evaluación.
# Un mismo cycle_at alimenta reconciliación de configuración, management y reduce_group_cycle por priority_group.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import uuid4

from ada.alarms.core import (
    ConfigurationClosure,
    DeactivationEffectIdFactory,
    DeactivationRequestIdFactory,
    EpisodeIdFactory,
    GroupLifecycleDecision,
    GroupLifecycleState,
    ManagementEffectIdFactory,
    OccurrenceClosureReason,
    OccurrenceIdFactory,
    PlannedAlarm,
    ReappearanceDueAtResolver,
    reconcile_group_configuration,
    reduce_group_cycle,
)
from ada.alarms.core.technical_incidents import (
    TechnicalIncident,
    TechnicalIncidentChange,
    reduce_initial_technical_incidents,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.adoption import (
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionPlan,
    plan_configuration_adoption,
)
from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycleResult
from ada.processes.alarm_runtime.inputs import (
    AlarmOperationalInputs,
)
from ada.processes.alarm_runtime.session import AlarmExecutionSession
from atlanticus.operational_data.core import normalize_utc_second


class AlarmLifecycleOrchestrationError(ValueError):
    pass


@runtime_checkable
class AlarmOperationalInputsProvider(Protocol):
    def read(
        self,
        *,
        session: AlarmExecutionSession,
        cycle_at: datetime,
    ) -> AlarmOperationalInputs: ...


@runtime_checkable
class AlarmLifecycleCycleExecutor(Protocol):
    def run(
        self,
        *,
        previous: AlarmLifecycleRuntimeState | None,
        session: AlarmExecutionSession,
        cycle: AlarmEvaluationCycleResult,
    ) -> AlarmLifecycleCycleResult: ...


@dataclass(frozen=True, slots=True)
class EmptyAlarmOperationalInputsProvider:
    def read(
        self,
        *,
        session: AlarmExecutionSession,
        cycle_at: datetime,
    ) -> AlarmOperationalInputs:
        if not isinstance(session, AlarmExecutionSession):
            raise TypeError('session must be an AlarmExecutionSession')
        normalize_utc_second(cycle_at, field_name='cycle_at')
        return AlarmOperationalInputs()


@dataclass(frozen=True, slots=True)
class AlarmLifecycleRuntimeState:
    configuration: EngineAlarmConfiguration
    groups: tuple[GroupLifecycleState, ...] = ()
    # Conserva errores sin ocurrencia incluso cuando el grupo físico está vacío.
    technical_incidents: tuple[TechnicalIncident, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, EngineAlarmConfiguration):
            raise TypeError('configuration must be an EngineAlarmConfiguration')
        if not isinstance(self.groups, tuple):
            raise TypeError('groups must be a tuple')
        keys: set[str] = set()
        normalized: list[GroupLifecycleState] = []
        for group in self.groups:
            if not isinstance(group, GroupLifecycleState):
                raise TypeError('groups must contain GroupLifecycleState values')
            if group.priority_group in keys:
                raise ValueError('groups must be unique by priority_group')
            keys.add(group.priority_group)
            normalized.append(group)
        object.__setattr__(
            self,
            'groups',
            tuple(sorted(normalized, key=lambda item: item.priority_group)),
        )
        if not isinstance(self.technical_incidents, tuple):
            raise TypeError('technical_incidents must be a tuple')
        incident_keys: set[AlarmIdentity] = set()
        for incident in self.technical_incidents:
            if not isinstance(incident, TechnicalIncident):
                raise TypeError('technical_incidents must contain TechnicalIncident values')
            if incident.alarm_identity in incident_keys:
                raise ValueError('technical_incidents must be unique by alarm identity')
            incident_keys.add(incident.alarm_identity)
        object.__setattr__(
            self,
            'technical_incidents',
            tuple(sorted(self.technical_incidents, key=lambda item: item.alarm_identity)),
        )

    def group_for(self, priority_group: str) -> GroupLifecycleState | None:
        if not isinstance(priority_group, str) or not priority_group.strip():
            raise ValueError('priority_group must be non-empty text')
        for group in self.groups:
            if group.priority_group == priority_group:
                return group
        return None


@dataclass(frozen=True, slots=True)
class AlarmLifecycleGroupResult:
    priority_group: str
    adoption_decision: GroupLifecycleDecision | None
    decision: GroupLifecycleDecision

    def __post_init__(self) -> None:
        if not isinstance(self.priority_group, str) or not self.priority_group.strip():
            raise ValueError('priority_group must be non-empty text')
        if self.adoption_decision is not None:
            if not isinstance(self.adoption_decision, GroupLifecycleDecision):
                raise TypeError('adoption_decision must be a GroupLifecycleDecision or None')
            if self.adoption_decision.state.priority_group != self.priority_group:
                raise ValueError('adoption decision priority_group must match group result')
        if not isinstance(self.decision, GroupLifecycleDecision):
            raise TypeError('decision must be a GroupLifecycleDecision')
        if self.decision.state.priority_group != self.priority_group:
            raise ValueError('cycle decision priority_group must match group result')


@dataclass(frozen=True, slots=True)
class AlarmLifecycleCycleResult:
    cycle_at: datetime
    inputs: AlarmOperationalInputs
    groups: tuple[AlarmLifecycleGroupResult, ...]
    state: AlarmLifecycleRuntimeState
    adoption_plan: ConfigurationAdoptionPlan | None = None
    technical_incident_changes: tuple[TechnicalIncidentChange, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'cycle_at',
            normalize_utc_second(self.cycle_at, field_name='cycle_at'),
        )
        if not isinstance(self.inputs, AlarmOperationalInputs):
            raise TypeError('inputs must be AlarmOperationalInputs')
        if not isinstance(self.groups, tuple) or not all(
            isinstance(item, AlarmLifecycleGroupResult) for item in self.groups
        ):
            raise TypeError('groups must contain AlarmLifecycleGroupResult values')
        keys = tuple(item.priority_group for item in self.groups)
        if keys != tuple(sorted(set(keys))):
            raise ValueError('group results must be unique and sorted by priority_group')
        if not isinstance(self.state, AlarmLifecycleRuntimeState):
            raise TypeError('state must be an AlarmLifecycleRuntimeState')
        if self.adoption_plan is not None:
            if not isinstance(self.adoption_plan, ConfigurationAdoptionPlan):
                raise TypeError('adoption_plan must be a ConfigurationAdoptionPlan or None')
            if self.state.configuration != self.adoption_plan.target:
                raise ValueError('lifecycle state configuration must match adoption target')
        if not isinstance(self.technical_incident_changes, tuple) or not all(
            isinstance(item, TechnicalIncidentChange)
            for item in self.technical_incident_changes
        ):
            raise TypeError('technical_incident_changes must contain TechnicalIncidentChange values')


def _occurrence_id(_identity: AlarmIdentity, _at: datetime) -> str:
    return f'occ-{uuid4().hex}'


def _episode_id(_priority_group: str, _at: datetime) -> str:
    return f'episode-{uuid4().hex}'


def _management_effect_id(_action) -> str:
    return f'management-effect-{uuid4().hex}'


def _deactivation_request_id(_action) -> str:
    return f'deactivation-request-{uuid4().hex}'


def _deactivation_effect_id(_request) -> str:
    return f'deactivation-effect-{uuid4().hex}'


@dataclass(slots=True)
class AlarmLifecycleCycle:
    inputs_provider: AlarmOperationalInputsProvider = field(
        default_factory=EmptyAlarmOperationalInputsProvider
    )
    occurrence_id_factory: OccurrenceIdFactory = field(default=_occurrence_id)
    episode_id_factory: EpisodeIdFactory = field(default=_episode_id)
    management_effect_id_factory: ManagementEffectIdFactory = field(
        default=_management_effect_id
    )
    deactivation_request_id_factory: DeactivationRequestIdFactory = field(
        default=_deactivation_request_id
    )
    deactivation_effect_id_factory: DeactivationEffectIdFactory = field(
        default=_deactivation_effect_id
    )

    def __post_init__(self) -> None:
        if not isinstance(self.inputs_provider, AlarmOperationalInputsProvider):
            raise TypeError('inputs_provider must implement AlarmOperationalInputsProvider')
        for factory_value, name in (
            (self.occurrence_id_factory, 'occurrence_id_factory'),
            (self.episode_id_factory, 'episode_id_factory'),
            (self.management_effect_id_factory, 'management_effect_id_factory'),
            (self.deactivation_request_id_factory, 'deactivation_request_id_factory'),
            (self.deactivation_effect_id_factory, 'deactivation_effect_id_factory'),
        ):
            if not callable(factory_value):
                raise TypeError(f'{name} must be callable')

    def run(
        self,
        *,
        previous: AlarmLifecycleRuntimeState | None,
        session: AlarmExecutionSession,
        cycle: AlarmEvaluationCycleResult,
    ) -> AlarmLifecycleCycleResult:
        if previous is not None and not isinstance(previous, AlarmLifecycleRuntimeState):
            raise TypeError('previous must be an AlarmLifecycleRuntimeState or None')
        if not isinstance(session, AlarmExecutionSession):
            raise TypeError('session must be an AlarmExecutionSession')
        if not isinstance(cycle, AlarmEvaluationCycleResult):
            raise TypeError('cycle must be an AlarmEvaluationCycleResult')
        self._validate_evaluations(session, cycle)
        adoption_plan = self._adoption_plan(previous, session)
        inputs = self.inputs_provider.read(session=session, cycle_at=cycle.cycle_at)
        if not isinstance(inputs, AlarmOperationalInputs):
            raise TypeError('inputs_provider must return AlarmOperationalInputs')
        self._validate_operational_inputs(session, inputs)
        group_keys = self._priority_groups(previous, session, inputs)
        group_results = tuple(
            self._run_group(
                priority_group,
                previous=previous,
                session=session,
                cycle=cycle,
                inputs=inputs,
                adoption_plan=adoption_plan,
            )
            for priority_group in group_keys
        )
        physical_occurrences = frozenset(
            alarm.alarm_identity
            for group in (
                (() if previous is None else previous.groups)
                + tuple(item.decision.state for item in group_results)
            )
            for alarm in group.alarms
            if alarm.occurrence is not None
        )
        # Deduplica eventos en el ciclo; la confirmación WAL será el siguiente incremento.
        incident_reduction = reduce_initial_technical_incidents(
            () if previous is None else previous.technical_incidents,
            evaluations=cycle.evaluations,
            executable_groups={
                entry.identity: entry.planned_alarm.priority_group
                for entry in session.entries
            },
            physical_occurrences=physical_occurrences,
            cycle_at=cycle.cycle_at,
        )
        state = AlarmLifecycleRuntimeState(
            configuration=session.configuration,
            technical_incidents=incident_reduction.open_incidents,
            groups=tuple(
                item.decision.state
                for item in group_results
                if _has_operational_state(item.decision.state)
            ),
        )
        return AlarmLifecycleCycleResult(
            cycle_at=cycle.cycle_at,
            inputs=inputs,
            groups=group_results,
            state=state,
            adoption_plan=adoption_plan,
            technical_incident_changes=incident_reduction.changes,
        )

    @staticmethod
    def _validate_evaluations(
        session: AlarmExecutionSession,
        cycle: AlarmEvaluationCycleResult,
    ) -> None:
        expected = tuple(entry.identity for entry in session.entries)
        actual = tuple(item.alarm_identity for item in cycle.evaluations)
        if actual != expected:
            raise AlarmLifecycleOrchestrationError(
                'evaluation identities must exactly follow the execution session'
            )

    @staticmethod
    def _adoption_plan(
        previous: AlarmLifecycleRuntimeState | None,
        session: AlarmExecutionSession,
    ) -> ConfigurationAdoptionPlan | None:
        if previous is None:
            return None
        source = previous.configuration
        target = session.configuration
        if source.resolution_key == target.resolution_key:
            if source != target:
                raise AlarmLifecycleOrchestrationError(
                    'same resolution_key cannot identify different lifecycle configurations'
                )
            return None
        plan = plan_configuration_adoption(source, target)
        if not plan.is_adoptable:
            rejected = ', '.join(
                f'{item.identity.canonical_key}:{item.rejection_reason.value}'
                for item in plan.rejected_changes
            )
            raise AlarmLifecycleOrchestrationError(
                f'configuration adoption is not lifecycle-compatible: {rejected}'
            )
        return plan

    def _run_group(
        self,
        priority_group: str,
        *,
        previous: AlarmLifecycleRuntimeState | None,
        session: AlarmExecutionSession,
        cycle: AlarmEvaluationCycleResult,
        inputs: AlarmOperationalInputs,
        adoption_plan: ConfigurationAdoptionPlan | None,
    ) -> AlarmLifecycleGroupResult:
        previous_group = None if previous is None else previous.group_for(priority_group)
        state = (
            GroupLifecycleState(priority_group=priority_group)
            if previous_group is None
            else previous_group
        )
        plans = tuple(
            entry.planned_alarm
            for entry in session.entries
            if entry.planned_alarm.priority_group == priority_group
        )
        adoption_decision = self._reconcile_group(
            state,
            priority_group=priority_group,
            plans=plans,
            cycle_at=cycle.cycle_at,
            adoption_plan=adoption_plan,
        )
        if adoption_decision is not None:
            state = adoption_decision.state
        identities = {plan.identity for plan in plans}
        evaluations = tuple(
            evaluation
            for evaluation in cycle.evaluations
            if evaluation.alarm_identity in identities
        )
        pending = tuple(
            item.request
            for item in inputs.pending_deactivation_requests
            if item.priority_group == priority_group
        )
        pending_ids = {item.request_id for item in pending}
        plan_by_identity = {plan.identity: plan for plan in plans}
        decision = reduce_group_cycle(
            state,
            cycle_at=cycle.cycle_at,
            planned_alarms=plans,
            evaluations=evaluations,
            occurrence_id_factory=self.occurrence_id_factory,
            episode_id_factory=self.episode_id_factory,
            management_actions=tuple(
                action
                for action in inputs.management_actions
                if action.alarm_identity in identities
            ),
            management_effect_id_factory=self.management_effect_id_factory,
            reappearance_due_at_resolver=_reappearance_due_at_resolver(plan_by_identity),
            pending_deactivation_requests=pending,
            deactivation_decisions=tuple(
                item for item in inputs.deactivation_decisions if item.request_id in pending_ids
            ),
            # Entrega al physical cycle los CLEARED ya producidos por Adoption en este
            # mismo ciclo para preservar causalidad; Core aplica la semántica del target plan.
            prior_deactivation_effect_changes=(
                ()
                if adoption_decision is None
                else adoption_decision.deactivation_effect_changes
            ),
            deactivation_request_id_factory=self.deactivation_request_id_factory,
            deactivation_effect_id_factory=self.deactivation_effect_id_factory,
        )
        return AlarmLifecycleGroupResult(
            priority_group=priority_group,
            adoption_decision=adoption_decision,
            decision=decision,
        )

    @staticmethod
    def _reconcile_group(
        state: GroupLifecycleState,
        *,
        priority_group: str,
        plans: tuple[PlannedAlarm, ...],
        cycle_at: datetime,
        adoption_plan: ConfigurationAdoptionPlan | None,
    ) -> GroupLifecycleDecision | None:
        if adoption_plan is None:
            return None
        changes = adoption_plan.changes_for_group(priority_group)
        actionable = tuple(
            item
            for item in changes
            if item.disposition is not ConfigurationAdoptionDisposition.UNCHANGED
        )
        if not actionable:
            return None
        closures = tuple(
            ConfigurationClosure(
                alarm_identity=item.identity,
                reason=(
                    OccurrenceClosureReason.CONFIGURATION_DISABLED
                    if item.disposition is ConfigurationAdoptionDisposition.DISABLED
                    else OccurrenceClosureReason.CONFIGURATION_REMOVED
                ),
                effective_at=cycle_at,
            )
            for item in actionable
            if item.disposition
            in {
                ConfigurationAdoptionDisposition.DISABLED,
                ConfigurationAdoptionDisposition.REMOVED,
            }
        )
        # Reconcilia la configuración sin interrumpir las gestiones ni la continuidad del grupo.
        return reconcile_group_configuration(
            state,
            effective_at=cycle_at,
            planned_alarms=plans,
            configuration_closures=closures,
        )

    @staticmethod
    def _priority_groups(
        previous: AlarmLifecycleRuntimeState | None,
        session: AlarmExecutionSession,
        inputs: AlarmOperationalInputs,
    ) -> tuple[str, ...]:
        keys = {entry.planned_alarm.priority_group for entry in session.entries}
        if previous is not None:
            keys.update(group.priority_group for group in previous.groups)
        keys.update(item.priority_group for item in inputs.pending_deactivation_requests)
        return tuple(sorted(keys))

    @staticmethod
    def _validate_operational_inputs(
        session: AlarmExecutionSession,
        inputs: AlarmOperationalInputs,
    ) -> None:
        identity_to_group = {
            entry.identity: entry.planned_alarm.priority_group for entry in session.entries
        }
        identities = set(identity_to_group)
        for action in inputs.management_actions:
            if action.alarm_identity not in identities:
                raise AlarmLifecycleOrchestrationError(
                    f'{action.alarm_identity.canonical_key}: management input alarm is not '
                    'executable in the current session'
                )
        for pending in inputs.pending_deactivation_requests:
            expected = identity_to_group.get(pending.request.alarm_identity)
            if expected is not None and expected != pending.priority_group:
                raise AlarmLifecycleOrchestrationError(
                    f'{pending.request.alarm_identity.canonical_key}: pending deactivation '
                    'priority_group does not match the current session'
                )


def _reappearance_due_at_resolver(
    plans: dict[AlarmIdentity, PlannedAlarm],
) -> ReappearanceDueAtResolver:
    def resolve(action) -> datetime | None:
        plan = plans.get(action.alarm_identity)
        if plan is None:
            raise AlarmLifecycleOrchestrationError(
                f'{action.alarm_identity.canonical_key}: management alarm is not executable'
            )
        seconds = plan.reappearance_after_seconds
        if seconds is None:
            return None
        return action.source_created_at + timedelta(seconds=seconds)

    return resolve


def _has_operational_state(state: GroupLifecycleState) -> bool:
    return state.episode is not None or bool(state.alarms)
