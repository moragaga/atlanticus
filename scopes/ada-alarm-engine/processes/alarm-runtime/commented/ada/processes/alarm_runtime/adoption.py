# Espejo pedagógico de la clasificación de cambios entre revisiones ejecutables de Alarm.
# Separa mutaciones compatibles, reconciliación de destinos e invariantes rechazadas por diseño.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.alarms.core import PlannedAlarm
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity, Criticality


class ConfigurationAdoptionPlanError(ValueError):
    pass


class ConfigurationAdoptionDisposition(StrEnum):
    UNCHANGED = 'unchanged'
    COMPATIBLE = 'compatible'
    ADDED = 'added'
    ENABLED = 'enabled'
    DISABLED = 'disabled'
    REMOVED = 'removed'
    REJECTED = 'rejected'


class ConfigurationAdoptionRejectionReason(StrEnum):
    PRIORITY_GROUP_IMMUTABLE = 'priority_group_immutable'
    C1_ROUTING_MUTATION_UNSUPPORTED = 'c1_routing_mutation_unsupported'
    C3_ROUTING_MUTATION_UNSUPPORTED = 'c3_routing_mutation_unsupported'


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionChange:
    identity: AlarmIdentity
    disposition: ConfigurationAdoptionDisposition
    rejection_reason: ConfigurationAdoptionRejectionReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, AlarmIdentity):
            raise TypeError('identity must be an AlarmIdentity')
        if not isinstance(self.disposition, ConfigurationAdoptionDisposition):
            raise TypeError('disposition must be a ConfigurationAdoptionDisposition')
        if self.disposition is ConfigurationAdoptionDisposition.REJECTED:
            if not isinstance(self.rejection_reason, ConfigurationAdoptionRejectionReason):
                raise ConfigurationAdoptionPlanError(
                    'rejected configuration change requires rejection_reason'
                )
        elif self.rejection_reason is not None:
            raise ConfigurationAdoptionPlanError(
                'rejection_reason is only valid for rejected configuration changes'
            )


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionPlan:
    source: EngineAlarmConfiguration
    target: EngineAlarmConfiguration
    changes: tuple[ConfigurationAdoptionChange, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, EngineAlarmConfiguration):
            raise TypeError('source must be an EngineAlarmConfiguration')
        if not isinstance(self.target, EngineAlarmConfiguration):
            raise TypeError('target must be an EngineAlarmConfiguration')
        if self.source.resolution_key == self.target.resolution_key:
            raise ConfigurationAdoptionPlanError(
                'source and target configuration resolution keys must differ'
            )
        if not isinstance(self.changes, tuple):
            raise TypeError('changes must be a tuple')
        if not all(isinstance(item, ConfigurationAdoptionChange) for item in self.changes):
            raise TypeError('changes must contain ConfigurationAdoptionChange values')
        identities = tuple(change.identity for change in self.changes)
        if len(identities) != len(set(identities)):
            raise ConfigurationAdoptionPlanError('configuration changes must be unique by identity')
        universe = set(self.source.defined_alarm_identities) | set(
            self.target.defined_alarm_identities
        )
        if set(identities) != universe:
            raise ConfigurationAdoptionPlanError(
                'configuration changes must cover source and target defined alarm identities'
            )
        object.__setattr__(
            self,
            'changes',
            tuple(sorted(self.changes, key=lambda item: item.identity.canonical_key)),
        )

    @property
    def is_adoptable(self) -> bool:
        return all(
            change.disposition is not ConfigurationAdoptionDisposition.REJECTED
            for change in self.changes
        )

    @property
    def rejected_changes(self) -> tuple[ConfigurationAdoptionChange, ...]:
        return tuple(
            change
            for change in self.changes
            if change.disposition is ConfigurationAdoptionDisposition.REJECTED
        )

    def changes_for_group(self, priority_group: str) -> tuple[ConfigurationAdoptionChange, ...]:
        if not isinstance(priority_group, str) or not priority_group.strip():
            raise ValueError('priority_group must be non-empty text')
        output: list[ConfigurationAdoptionChange] = []
        for change in self.changes:
            source = _plan_for(self.source, change.identity)
            target = _plan_for(self.target, change.identity)
            if (
                source is not None
                and source.priority_group == priority_group
                or target is not None
                and target.priority_group == priority_group
            ):
                output.append(change)
        return tuple(output)


def plan_configuration_adoption(
    source: EngineAlarmConfiguration,
    target: EngineAlarmConfiguration,
) -> ConfigurationAdoptionPlan:
    if not isinstance(source, EngineAlarmConfiguration):
        raise TypeError('source must be an EngineAlarmConfiguration')
    if not isinstance(target, EngineAlarmConfiguration):
        raise TypeError('target must be an EngineAlarmConfiguration')
    universe = set(source.defined_alarm_identities) | set(target.defined_alarm_identities)
    changes = tuple(_classify_change(source, target, identity) for identity in sorted(universe))
    return ConfigurationAdoptionPlan(source=source, target=target, changes=changes)


def _classify_change(
    source: EngineAlarmConfiguration,
    target: EngineAlarmConfiguration,
    identity: AlarmIdentity,
) -> ConfigurationAdoptionChange:
    source_defined = identity in source.defined_alarm_identities
    target_defined = identity in target.defined_alarm_identities
    if not source_defined:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=ConfigurationAdoptionDisposition.ADDED,
        )
    if not target_defined:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=ConfigurationAdoptionDisposition.REMOVED,
        )
    source_plan = _plan_for(source, identity)
    target_plan = _plan_for(target, identity)
    if source_plan is None:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=(
                ConfigurationAdoptionDisposition.ENABLED
                if target_plan is not None
                else ConfigurationAdoptionDisposition.UNCHANGED
            ),
        )
    if target_plan is None:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=ConfigurationAdoptionDisposition.DISABLED,
        )
    rejection_reason = _rejection_reason(source_plan, target_plan)
    if rejection_reason is not None:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=ConfigurationAdoptionDisposition.REJECTED,
            rejection_reason=rejection_reason,
        )
    # Cambiar criticidad u origen conserva la occurrence; restringir sólo destinos C1/C3 aislados.
    if (
        source_plan.criticality is target_plan.criticality
        and source_plan.routing.destinations != target_plan.routing.destinations
    ):
        routing_rejection = _routing_rejection_reason(source_plan.criticality)
        if routing_rejection is not None:
            return ConfigurationAdoptionChange(
                identity=identity,
                disposition=ConfigurationAdoptionDisposition.REJECTED,
                rejection_reason=routing_rejection,
            )
    return ConfigurationAdoptionChange(
        identity=identity,
        disposition=(
            ConfigurationAdoptionDisposition.UNCHANGED
            if _runtime_semantics_equal(source, target, identity)
            else ConfigurationAdoptionDisposition.COMPATIBLE
        ),
    )


def _rejection_reason(
    source: PlannedAlarm,
    target: PlannedAlarm,
) -> ConfigurationAdoptionRejectionReason | None:
    # priority_group pertenece a la identidad operacional vigente y no se migra entre grupos.
    if source.priority_group != target.priority_group:
        return ConfigurationAdoptionRejectionReason.PRIORITY_GROUP_IMMUTABLE
    return None


def _routing_rejection_reason(
    criticality: Criticality,
) -> ConfigurationAdoptionRejectionReason | None:
    if criticality is Criticality.C1:
        return ConfigurationAdoptionRejectionReason.C1_ROUTING_MUTATION_UNSUPPORTED
    if criticality is Criticality.C3:
        return ConfigurationAdoptionRejectionReason.C3_ROUTING_MUTATION_UNSUPPORTED
    return None


def _runtime_semantics_equal(
    source: EngineAlarmConfiguration,
    target: EngineAlarmConfiguration,
    identity: AlarmIdentity,
) -> bool:
    source_plan = _plan_for(source, identity)
    target_plan = _plan_for(target, identity)
    if source_plan is None or target_plan is None:
        return False
    return (
        source_plan.kind is target_plan.kind
        and source_plan.criticality is target_plan.criticality
        # Cambiar el flag es semántica Runtime y debe clasificarse como COMPATIBLE, no UNCHANGED.
        and source_plan.is_special_condition is target_plan.is_special_condition
        and source_plan.priority_group == target_plan.priority_group
        and source_plan.priority_order == target_plan.priority_order
        and source_plan.evaluator_key == target_plan.evaluator_key
        and source_plan.routing == target_plan.routing
        and source_plan.deactivation_policy == target_plan.deactivation_policy
        and source_plan.reappearance_after_seconds == target_plan.reappearance_after_seconds
        and source_plan.reappearance_special_conditions
        == target_plan.reappearance_special_conditions
        and source.parameters_by_alarm.get(identity, {})
        == target.parameters_by_alarm.get(identity, {})
    )


def _plan_for(
    configuration: EngineAlarmConfiguration,
    identity: AlarmIdentity,
) -> PlannedAlarm | None:
    for plan in configuration.planned_alarms:
        if plan.identity == identity:
            return plan
    return None
