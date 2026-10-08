from __future__ import annotations

from typing import Protocol

from ada.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
)
from ada.alarms.materialization.delivery import DeliveryAlarmConfiguration
from ada.alarms.materialization.engine import EngineAlarmConfiguration
from ada.alarms.materialization.modeler import (
    ModelerAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedModelerAlarm,
    ResolvedModelerMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
)


from ada.alarms.materialization.resolution import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)
from ada.contracts.alarms import (
    AlarmConfiguration,
    AlarmDefinition,
    AlarmVisualTarget,
    Criticality,
    DeactivationLimit,
    MessageDefinition,
    VisibilityMode,
)
from ada.contracts.tools.enums import ToolConfigurationKind
from ada.contracts.tools.errors import ToolConfigurationValidationError
from ada.contracts.tools.structure import ToolStructure


class _ToolCatalogEntry(Protocol):
    kind: ToolConfigurationKind
    structure: ToolStructure


class _ConfirmedToolCatalog(Protocol):
    revision: str

    def get(self, tool_key: str) -> _ToolCatalogEntry | None: ...


class _DeactivationDefinition(Protocol):
    enabled: bool
    max_duration_hours: DeactivationLimit
    approval_required: bool


def resolve_alarm_configuration(
    configuration: AlarmConfiguration,
    alarm_configuration_revision: str,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> AlarmConfigurationResolution:
    if not isinstance(configuration, AlarmConfiguration):
        raise TypeError('configuration must be an AlarmConfiguration')
    catalog_revision = _catalog_revision(confirmed_tool_catalog)
    resolution_key = AlarmResolutionKey(
        alarm_configuration_revision=alarm_configuration_revision,
        confirmed_tool_catalog_revision=catalog_revision,
    )
    findings = _collect_reference_findings(configuration, confirmed_tool_catalog)
    if findings:
        return AlarmConfigurationResolution(
            resolution_key=resolution_key,
            status=AlarmResolutionStatus.BLOCKED,
            findings=findings,
        )
    modeler = _materialize_modeler(
        configuration=configuration,
        resolution_key=resolution_key,
        confirmed_tool_catalog=confirmed_tool_catalog,
    )
    return AlarmConfigurationResolution(
        resolution_key=resolution_key,
        status=AlarmResolutionStatus.READY,
        findings=(),
        engine_configuration=_materialize_engine(configuration=configuration, resolution_key=resolution_key),
        modeler_configuration=modeler,
        delivery_configuration=_materialize_delivery(modeler_configuration=modeler, resolution_key=resolution_key),
    )


def _catalog_revision(catalog: _ConfirmedToolCatalog) -> str:
    revision = getattr(catalog, 'revision', None)
    if not isinstance(revision, str):
        raise TypeError('confirmed_tool_catalog revision must be a string')
    if not revision.strip():
        raise ValueError('confirmed_tool_catalog revision must not be empty')
    if not callable(getattr(catalog, 'get', None)):
        raise TypeError('confirmed_tool_catalog must provide get(tool_key)')
    return revision


def _collect_reference_findings(
    configuration: AlarmConfiguration,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> tuple[AlarmResolutionFinding, ...]:
    findings: list[AlarmResolutionFinding] = []
    for rule in configuration.rules:
        path = _rule_path(rule)
        referenced = [(rule.escalation.origin_tool_key, f'{path}.escalation.origin_tool_key')]
        referenced.extend(
            (step.target_tool_key, f'{path}.escalation.steps[{step.step_order}].target_tool_key')
            for step in rule.escalation.steps
        )
        referenced.extend(
            (target.tool_key, f'{path}.visual_targets[{target.tool_key}].tool_key')
            for target in rule.visual_targets
        )
        for tool_key, field_path in referenced:
            if confirmed_tool_catalog.get(tool_key) is None:
                findings.append(
                    _blocking_finding(
                        code='tool_reference_not_found',
                        message=f'Tool reference {tool_key!r} is missing from the pinned Tool manifest',
                        rule=rule,
                        field_path=field_path,
                        reference_key=tool_key,
                    )
                )
        for target in rule.visual_targets:
            entry = confirmed_tool_catalog.get(target.tool_key)
            if entry is None:
                continue
            base_path = f'{path}.visual_targets[{target.tool_key}]'
            for component_key in target.component_keys:
                try:
                    entry.structure.component(component_key)
                except ToolConfigurationValidationError:
                    findings.append(
                        _blocking_finding(
                            code='visual_reference_not_found',
                            message=f'Unknown component {component_key!r}',
                            rule=rule,
                            field_path=f'{base_path}.component_keys[{component_key}]',
                            reference_key=component_key,
                        )
                    )
            for subcomponent in target.subcomponents:
                reference_key = f'{subcomponent.owner_component_key}/{subcomponent.subcomponent_key}'
                try:
                    entry.structure.component(subcomponent.owner_component_key).subcomponent(
                        subcomponent.subcomponent_key
                    )
                except ToolConfigurationValidationError:
                    findings.append(
                        _blocking_finding(
                            code='visual_reference_not_found',
                            message=f'Unknown subcomponent {reference_key!r}',
                            rule=rule,
                            field_path=f'{base_path}.subcomponents[{reference_key}]',
                            reference_key=reference_key,
                        )
                    )
    return tuple(findings)

def _materialize_engine(
    *,
    configuration: AlarmConfiguration,
    resolution_key: AlarmResolutionKey,
) -> EngineAlarmConfiguration:
    active_rules = tuple(rule for rule in configuration.rules if rule.is_active)
    planned_alarms = tuple(
        PlannedAlarm(
            identity=rule.identity,
            kind=rule.kind,
            criticality=rule.criticality,
            is_special_condition=rule.is_special_condition,
            priority_group=rule.priority_group,
            priority_order=rule.priority_order,
            evaluator_key=rule.evaluator_key,
            alarm_configuration_revision=resolution_key.alarm_configuration_revision,
            tool_registry_revision=resolution_key.confirmed_tool_catalog_revision,
            routing=_materialize_routing(rule),
            deactivation_policy=(
                DeactivationPolicy(approval_required=rule.default_deactivation.approval_required)
                if rule.default_deactivation.enabled
                else None
            ),
            reappearance_after_seconds=(
                None
                if rule.reappearance.after_minutes is None
                else rule.reappearance.after_minutes * 60
            ),
            reappearance_special_conditions=rule.reappearance.special_conditions,
        )
        for rule in active_rules
    )
    return EngineAlarmConfiguration(
        resolution_key=resolution_key,
        defined_alarm_identities=tuple(rule.identity for rule in configuration.rules),
        planned_alarms=planned_alarms,
        parameters_by_alarm={rule.identity: rule.parameters for rule in active_rules},
    )


def _materialize_routing(rule: AlarmDefinition) -> AlarmRouting:
    enabled_steps = tuple(
        step
        for step in sorted(rule.escalation.steps, key=lambda item: item.step_order)
        if step.is_enabled
    )
    if rule.criticality is Criticality.C1:
        destinations = tuple(
            RoutingDestination(tool_key=step.target_tool_key) for step in enabled_steps
        )
    elif rule.criticality is Criticality.C2:
        elapsed_minutes = 0
        materialized: list[RoutingDestination] = []
        for step in enabled_steps:
            wait = step.wait_minutes_from_previous_step
            if wait is None or wait <= 0:
                raise ValueError('C2 routing must be validated before materialization')
            elapsed_minutes += wait
            materialized.append(
                RoutingDestination(
                    tool_key=step.target_tool_key,
                    delay_seconds=elapsed_minutes * 60,
                )
            )
        destinations = tuple(materialized)
    else:
        destinations = ()
    return AlarmRouting(
        origin_tool_key=rule.escalation.origin_tool_key,
        destinations=destinations,
    )


def _materialize_modeler(
    *,
    configuration: AlarmConfiguration,
    resolution_key: AlarmResolutionKey,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> ModelerAlarmConfiguration:
    messages_by_key = {message.message_key: message for message in configuration.messages}
    return ModelerAlarmConfiguration(
        resolution_key=resolution_key,
        alarms=tuple(
            _materialize_modeler_alarm(
                rule=rule,
                messages_by_key=messages_by_key,
                confirmed_tool_catalog=confirmed_tool_catalog,
            )
            for rule in configuration.rules
        ),
    )


def _materialize_modeler_alarm(
    *,
    rule: AlarmDefinition,
    messages_by_key: dict[str, MessageDefinition],
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> ResolvedModelerAlarm:
    return ResolvedModelerAlarm(
        identity=rule.identity,
        is_active=rule.is_active,
        visibility_mode=rule.visibility_mode,
        display_name=rule.display_name,
        title=rule.title,
        cause_template=rule.cause_template,
        kind=rule.kind,
        criticality=rule.criticality,
        business_category=rule.business_category,
        operational_areas=rule.operational_areas,
        color=rule.color,
        priority_group=rule.priority_group,
        priority_order=rule.priority_order,
        default_deactivation_policy=_materialize_deactivation_policy(rule.default_deactivation),
        messages=tuple(
            _materialize_message(
                message=message,
                default_deactivation=rule.default_deactivation,
            )
            for message_key in rule.message_keys
            if (message := messages_by_key[message_key]).is_active
        ),
        visual_targets=tuple(
            _materialize_visual_target(target, confirmed_tool_catalog)
            for target in rule.visual_targets
        ),
    )


def _materialize_delivery(
    *,
    modeler_configuration: ModelerAlarmConfiguration,
    resolution_key: AlarmResolutionKey,
) -> DeliveryAlarmConfiguration:
    tool_keys = {
        target.tool_key
        for alarm in modeler_configuration.alarms
        if alarm.is_active and alarm.visibility_mode is VisibilityMode.VISIBLE
        for target in alarm.visual_targets
    }
    return DeliveryAlarmConfiguration(
        resolution_key=resolution_key,
        publication_tool_keys=tuple(sorted(tool_keys)),
    )


def _materialize_message(
    *,
    message: MessageDefinition,
    default_deactivation: _DeactivationDefinition,
) -> ResolvedModelerMessage:
    deactivation = (
        default_deactivation
        if message.deactivation_override is None
        else message.deactivation_override
    )
    return ResolvedModelerMessage(
        message_key=message.message_key,
        display_text=message.display_text,
        deactivation_policy=_materialize_deactivation_policy(deactivation),
    )


def _materialize_deactivation_policy(
    definition: _DeactivationDefinition,
) -> ResolvedDeactivationPolicy:
    return ResolvedDeactivationPolicy(
        enabled=definition.enabled,
        max_duration_hours=definition.max_duration_hours,
        approval_required=definition.approval_required,
    )


def _materialize_visual_target(
    target: AlarmVisualTarget,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> ResolvedVisualTarget:
    entry = confirmed_tool_catalog.get(target.tool_key)
    if entry is None:
        raise ValueError('visual target must be validated before materialization')
    return ResolvedVisualTarget(
        tool_key=target.tool_key,
        tool_kind=entry.kind,
        component_keys=target.component_keys,
        subcomponents=tuple(
            ResolvedVisualSubcomponentTarget(
                owner_component_key=subcomponent.owner_component_key,
                subcomponent_key=subcomponent.subcomponent_key,
            )
            for subcomponent in target.subcomponents
        ),
        process_projection_mode=target.process_projection_mode,
    )


def _blocking_finding(
    *,
    code: str,
    message: str,
    rule: AlarmDefinition,
    field_path: str,
    reference_key: str,
) -> AlarmResolutionFinding:
    return AlarmResolutionFinding(
        code=code,
        severity=AlarmResolutionFindingSeverity.BLOCKING,
        message=message,
        alarm_identity=rule.identity,
        field_path=field_path,
        reference_key=reference_key,
    )


def _rule_path(rule: AlarmDefinition) -> str:
    return f'rules[{rule.identity.canonical_key}]'
