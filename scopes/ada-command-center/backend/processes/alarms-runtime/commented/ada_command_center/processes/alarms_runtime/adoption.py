# Planificación pura de la transición entre DOS artefactos exactos; no persiste ni ejecuta cambios.
# La unión de identidades definidas evita confundir nuevas Rules, Rules deshabilitadas y Rules eliminadas.
# ADDED y ENABLED sólo se clasifican aquí: el ejecutor durable todavía no implementa esas transiciones.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada_command_center.alarms.core import PlannedAlarm
from ada_command_center.alarms.materialization.artifact_reference import (
    AlarmConfigurationArtifactRef,
)
from ada.contracts.alarms import AlarmIdentity, Criticality
from ada_command_center.processes.alarms_runtime.session import AlarmExecutionSession


class AlarmConfigurationRevisionError(ValueError):
    pass


class ConfigurationAdoptionPlanError(ValueError):
    pass


class ConfigurationAdoptionDisposition(StrEnum):
    UNCHANGED = 'unchanged'
    COMPATIBLE = 'compatible'
    ADDED = 'added'
    ENABLED = 'enabled'
    DISABLED = 'disabled'
    REMOVED = 'removed'
    STRUCTURAL_RESET = 'structural_reset'
    REJECTED = 'rejected'


class ConfigurationAdoptionRejectionReason(StrEnum):
    PRIORITY_GROUP_CHANGED = 'priority_group_changed'
    ALARM_KIND_CHANGED = 'alarm_kind_changed'
    EVALUATOR_CHANGED = 'evaluator_changed'
    C1_ROUTING_MUTATION_UNSUPPORTED = 'c1_routing_mutation_unsupported'
    C3_ROUTING_MUTATION_UNSUPPORTED = 'c3_routing_mutation_unsupported'


@dataclass(frozen=True, slots=True)
# Cada revisión de planificación queda vinculada a un artifact_ref exacto, no sólo a Rn/Cn.
class AlarmConfigurationRevision:
    artifact_ref: AlarmConfigurationArtifactRef
    defined_alarm_identities: tuple[AlarmIdentity, ...]
    session: AlarmExecutionSession

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_ref, AlarmConfigurationArtifactRef):
            raise TypeError('artifact_ref must be an AlarmConfigurationArtifactRef')
        if not isinstance(self.defined_alarm_identities, tuple):
            raise TypeError('defined_alarm_identities must be a tuple')
        identities = self.defined_alarm_identities
        if not all(isinstance(item, AlarmIdentity) for item in identities):
            raise TypeError('defined_alarm_identities must contain AlarmIdentity values')
        if len(identities) != len(set(identities)):
            raise AlarmConfigurationRevisionError('defined alarm identities must be unique')
        if not isinstance(self.session, AlarmExecutionSession):
            raise TypeError('session must be AlarmExecutionSession')
        if self.session.alarm_configuration_revision != self.alarm_configuration_revision:
            raise AlarmConfigurationRevisionError(
                'execution session alarm configuration revision does not match artifact'
            )
        if self.session.tool_registry_revision != self.tool_registry_revision:
            raise AlarmConfigurationRevisionError(
                'execution session tool registry revision does not match artifact'
            )
        if not set(self.session.identities) <= set(identities):
            raise AlarmConfigurationRevisionError(
                'execution session alarms must be defined by the configuration revision'
            )
        object.__setattr__(
            self,
            'defined_alarm_identities',
            tuple(sorted(identities, key=lambda item: item.canonical_key)),
        )

    @property
    def alarm_configuration_revision(self) -> str:
        return self.artifact_ref.resolution_key.alarm_configuration_revision

    @property
    def tool_registry_revision(self) -> str:
        return self.artifact_ref.resolution_key.confirmed_tool_catalog_revision

    @property
    def revision_key(self) -> tuple[str, str]:
        return self.alarm_configuration_revision, self.tool_registry_revision

    def is_defined(self, identity: AlarmIdentity) -> bool:
        _require_identity(identity)
        return identity in self.defined_alarm_identities

    def is_executable(self, identity: AlarmIdentity) -> bool:
        _require_identity(identity)
        return identity in self.session.identities

    def plan_for(self, identity: AlarmIdentity) -> PlannedAlarm | None:
        _require_identity(identity)
        for entry in self.session.entries:
            if entry.identity == identity:
                return entry.planned_alarm
        return None


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionChange:
    identity: AlarmIdentity
    disposition: ConfigurationAdoptionDisposition
    rejection_reason: ConfigurationAdoptionRejectionReason | None = None

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        if not isinstance(self.disposition, ConfigurationAdoptionDisposition):
            raise TypeError('disposition must be ConfigurationAdoptionDisposition')
        if self.rejection_reason is not None and not isinstance(
            self.rejection_reason, ConfigurationAdoptionRejectionReason
        ):
            raise TypeError('rejection_reason must be ConfigurationAdoptionRejectionReason or None')
        if self.disposition is ConfigurationAdoptionDisposition.REJECTED:
            if self.rejection_reason is None:
                raise ConfigurationAdoptionPlanError(
                    'rejected configuration change requires rejection_reason'
                )
        elif self.rejection_reason is not None:
            raise ConfigurationAdoptionPlanError(
                'rejection_reason is only valid for rejected configuration changes'
            )


@dataclass(frozen=True, slots=True)
# El plan exige cubrir la UNIÓN definida en origen y destino, incluso Rules inactivas.
class ConfigurationAdoptionPlan:
    source: AlarmConfigurationRevision
    target: AlarmConfigurationRevision
    changes: tuple[ConfigurationAdoptionChange, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source, AlarmConfigurationRevision):
            raise TypeError('source must be AlarmConfigurationRevision')
        if not isinstance(self.target, AlarmConfigurationRevision):
            raise TypeError('target must be AlarmConfigurationRevision')
        if self.source.artifact_ref.source_key != self.target.artifact_ref.source_key:
            raise ConfigurationAdoptionPlanError('source and target must have the same source_key')
        if self.source.artifact_ref.result_id == self.target.artifact_ref.result_id:
            if self.source.artifact_ref != self.target.artifact_ref:
                raise ConfigurationAdoptionPlanError(
                    'same result_id cannot identify conflicting materialization artifacts'
                )
            raise ConfigurationAdoptionPlanError('source and target artifacts must differ')
        changes = tuple(self.changes)
        if not all(isinstance(item, ConfigurationAdoptionChange) for item in changes):
            raise TypeError('changes must contain ConfigurationAdoptionChange values')
        identities = tuple(change.identity for change in changes)
        if len(identities) != len(set(identities)):
            raise ConfigurationAdoptionPlanError('configuration changes must be unique by identity')
        universe = set(self.source.defined_alarm_identities) | set(
            self.target.defined_alarm_identities
        )
        if set(identities) != universe:
            raise ConfigurationAdoptionPlanError(
                'configuration changes must cover source and target defined alarm identities'
            )
        for change in changes:
            self._validate_change(change)
        object.__setattr__(
            self,
            'changes',
            tuple(sorted(changes, key=lambda item: item.identity.canonical_key)),
        )

    @property
    def is_adoptable(self) -> bool:
        return all(
            change.disposition is not ConfigurationAdoptionDisposition.REJECTED
            for change in self.changes
        )

    @property
    def requires_execution_upgrade(self) -> bool:
        return any(
            change.disposition
            in {
                ConfigurationAdoptionDisposition.ADDED,
                ConfigurationAdoptionDisposition.ENABLED,
            }
            or (
                change.disposition is ConfigurationAdoptionDisposition.REMOVED
                and not self.source.is_executable(change.identity)
            )
            for change in self.changes
        )

    @property
    def rejected_changes(self) -> tuple[ConfigurationAdoptionChange, ...]:
        return tuple(
            change
            for change in self.changes
            if change.disposition is ConfigurationAdoptionDisposition.REJECTED
        )

    @property
    def structural_reset_groups(self) -> tuple[str, ...]:
        groups = {
            self.source.plan_for(change.identity).priority_group
            for change in self.changes
            if change.disposition is ConfigurationAdoptionDisposition.STRUCTURAL_RESET
        }
        return tuple(sorted(groups))

    # Esta validación evita que un plan construido manualmente suplante ADDED, ENABLED o REMOVED.
    def _validate_change(self, change: ConfigurationAdoptionChange) -> None:
        source_defined = self.source.is_defined(change.identity)
        target_defined = self.target.is_defined(change.identity)
        source_plan = self.source.plan_for(change.identity)
        target_plan = self.target.plan_for(change.identity)
        disposition = change.disposition
        if disposition is ConfigurationAdoptionDisposition.ADDED:
            if source_defined or not target_defined:
                raise ConfigurationAdoptionPlanError(
                    'added alarm must be absent in source and defined in target'
                )
            return
        if disposition is ConfigurationAdoptionDisposition.ENABLED:
            if not source_defined or source_plan is not None or target_plan is None:
                raise ConfigurationAdoptionPlanError(
                    'enabled alarm must be disabled in source and executable in target'
                )
            return
        if disposition is ConfigurationAdoptionDisposition.UNCHANGED and source_plan is None:
            if not source_defined or not target_defined or target_plan is not None:
                raise ConfigurationAdoptionPlanError(
                    'unchanged disabled alarm must remain defined and disabled'
                )
            return
        if source_plan is None:
            if (
                disposition is ConfigurationAdoptionDisposition.REMOVED
                and source_defined
                and not target_defined
            ):
                return
            raise ConfigurationAdoptionPlanError(
                'configuration change requires an executable source alarm'
            )
        if disposition in {
            ConfigurationAdoptionDisposition.UNCHANGED,
            ConfigurationAdoptionDisposition.COMPATIBLE,
            ConfigurationAdoptionDisposition.STRUCTURAL_RESET,
            ConfigurationAdoptionDisposition.REJECTED,
        }:
            if target_plan is None:
                raise ConfigurationAdoptionPlanError(
                    f'{change.identity.canonical_key}: target execution plan is required for '
                    f'{disposition.value}'
                )
            return
        if target_plan is not None:
            raise ConfigurationAdoptionPlanError(
                f'{change.identity.canonical_key}: {disposition.value} alarm must not be '
                'executable in target revision'
            )
        if disposition is ConfigurationAdoptionDisposition.DISABLED and not target_defined:
            raise ConfigurationAdoptionPlanError(
                f'{change.identity.canonical_key}: disabled alarm must remain defined in target '
                'revision'
            )
        if disposition is ConfigurationAdoptionDisposition.REMOVED and target_defined:
            raise ConfigurationAdoptionPlanError(
                f'{change.identity.canonical_key}: removed alarm must not be defined in target '
                'revision'
            )


# La clasificación es pura y determinista; no escribe WAL ni selecciona candidatos automáticamente.
def plan_configuration_adoption(
    source: AlarmConfigurationRevision,
    target: AlarmConfigurationRevision,
) -> ConfigurationAdoptionPlan:
    if not isinstance(source, AlarmConfigurationRevision):
        raise TypeError('source must be AlarmConfigurationRevision')
    if not isinstance(target, AlarmConfigurationRevision):
        raise TypeError('target must be AlarmConfigurationRevision')
    universe = set(source.defined_alarm_identities) | set(target.defined_alarm_identities)
    changes = tuple(_classify_change(source, target, identity) for identity in sorted(universe))
    return ConfigurationAdoptionPlan(source=source, target=target, changes=changes)


# Distingue nueva definición, activación, desactivación y eliminación sin inferir INVALID como REMOVED.
def _classify_change(
    source: AlarmConfigurationRevision,
    target: AlarmConfigurationRevision,
    identity: AlarmIdentity,
) -> ConfigurationAdoptionChange:
    source_defined = source.is_defined(identity)
    target_defined = target.is_defined(identity)
    if not source_defined:
        return ConfigurationAdoptionChange(
            identity=identity, disposition=ConfigurationAdoptionDisposition.ADDED
        )
    if not target_defined:
        return ConfigurationAdoptionChange(
            identity=identity, disposition=ConfigurationAdoptionDisposition.REMOVED
        )
    source_plan = source.plan_for(identity)
    target_plan = target.plan_for(identity)
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
            identity=identity, disposition=ConfigurationAdoptionDisposition.DISABLED
        )
    rejection_reason = _rejection_reason(source_plan, target_plan)
    if rejection_reason is not None:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=ConfigurationAdoptionDisposition.REJECTED,
            rejection_reason=rejection_reason,
        )
    if source_plan.criticality is not target_plan.criticality:
        return ConfigurationAdoptionChange(
            identity=identity,
            disposition=ConfigurationAdoptionDisposition.STRUCTURAL_RESET,
        )
    if source_plan.routing != target_plan.routing:
        routing_rejection = _routing_rejection_reason(source_plan.criticality)
        if routing_rejection is not None:
            return ConfigurationAdoptionChange(
                identity=identity,
                disposition=ConfigurationAdoptionDisposition.REJECTED,
                rejection_reason=routing_rejection,
            )
    disposition = (
        ConfigurationAdoptionDisposition.UNCHANGED
        if _runtime_semantics_equal(source, target, identity)
        else ConfigurationAdoptionDisposition.COMPATIBLE
    )
    return ConfigurationAdoptionChange(identity=identity, disposition=disposition)


def _rejection_reason(
    source: PlannedAlarm,
    target: PlannedAlarm,
) -> ConfigurationAdoptionRejectionReason | None:
    if source.priority_group != target.priority_group:
        return ConfigurationAdoptionRejectionReason.PRIORITY_GROUP_CHANGED
    if source.kind is not target.kind:
        return ConfigurationAdoptionRejectionReason.ALARM_KIND_CHANGED
    if source.evaluator_key != target.evaluator_key:
        return ConfigurationAdoptionRejectionReason.EVALUATOR_CHANGED
    return None


def _routing_rejection_reason(
    criticality: Criticality,
) -> ConfigurationAdoptionRejectionReason | None:
    if criticality is Criticality.C1:
        return ConfigurationAdoptionRejectionReason.C1_ROUTING_MUTATION_UNSUPPORTED
    if criticality is Criticality.C3:
        return ConfigurationAdoptionRejectionReason.C3_ROUTING_MUTATION_UNSUPPORTED
    return None


# Conserva la comparación operacional actual; reappearance y nuevas políticas siguen fuera de este incremento.
def _runtime_semantics_equal(
    source: AlarmConfigurationRevision,
    target: AlarmConfigurationRevision,
    identity: AlarmIdentity,
) -> bool:
    source_plan = source.plan_for(identity)
    target_plan = target.plan_for(identity)
    if source_plan is None or target_plan is None:
        return False
    source_entry = source.session.entry_for(identity)
    target_entry = target.session.entry_for(identity)
    return (
        source_plan.kind is target_plan.kind
        and source_plan.criticality is target_plan.criticality
        and source_plan.priority_group == target_plan.priority_group
        and source_plan.priority_order == target_plan.priority_order
        and source_plan.evaluator_key == target_plan.evaluator_key
        and source_plan.routing == target_plan.routing
        and source_plan.deactivation_policy == target_plan.deactivation_policy
        and source_entry.parameters == target_entry.parameters
    )


def _require_identity(identity: AlarmIdentity) -> None:
    if not isinstance(identity, AlarmIdentity):
        raise TypeError('identity must be AlarmIdentity')
