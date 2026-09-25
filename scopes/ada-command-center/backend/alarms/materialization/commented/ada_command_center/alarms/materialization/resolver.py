# Espejo pedagógico del resolver puro B.2.
# El código ejecutable es equivalente al archivo productivo; sólo se agregan comentarios explicativos.

from __future__ import annotations

from typing import Protocol

from ada.web.tools.enums import ToolConfigurationKind
from ada.web.tools.errors import ToolConfigurationValidationError
from ada.web.tools.structure import ToolStructure
from ada_command_center.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
)
from ada_command_center.alarms.materialization.delivery import (
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
    ResolvedDeliveryMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
)
from ada_command_center.alarms.materialization.qualification import (
    EvaluatorQualificationCatalog,
    ToolReconciliationQualification,
)
from ada_command_center.alarms.materialization.resolution import (
    AlarmConfigurationResolution,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)
from ada_command_center.alarms.materialization.runtime import RuntimeAlarmConfiguration
from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmDefinition,
    AlarmVisualTarget,
    Criticality,
    MessageDefinition,
)


# Describe sólo la superficie del entry que B.2 necesita; no acopla el resolver al package operacional del catálogo.
class _ToolCatalogEntry(Protocol):
    kind: ToolConfigurationKind
    structure: ToolStructure


# El snapshot confirmado se consume por contrato estructural: revision exacta y lookup por tool_key.
class _ConfirmedToolCatalog(Protocol):
    revision: str

    def get(self, tool_key: str) -> _ToolCatalogEntry | None: ...


# Unifica estructuralmente las policies authored de Rule y Message para materializarlas sin adapters.
class _DeactivationDefinition(Protocol):
    enabled: bool
    max_duration_hours: int | None
    approval_required: bool


# Punto de entrada puro B.2: valida el candidato completo y materializa Runtime + Delivery de forma atómica.
def resolve_alarm_configuration(
    configuration: AlarmConfiguration,
    alarm_configuration_revision: str,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
    tool_qualification: ToolReconciliationQualification,
    evaluator_qualification: EvaluatorQualificationCatalog,
) -> AlarmConfigurationResolution:
    if not isinstance(configuration, AlarmConfiguration):
        raise TypeError('configuration must be an AlarmConfiguration')
    if not isinstance(tool_qualification, ToolReconciliationQualification):
        raise TypeError('tool_qualification must be a ToolReconciliationQualification')
    if not isinstance(evaluator_qualification, EvaluatorQualificationCatalog):
        raise TypeError('evaluator_qualification must be an EvaluatorQualificationCatalog')
    catalog_revision = _catalog_revision(confirmed_tool_catalog)
    resolution_key = AlarmResolutionKey(
        alarm_configuration_revision=alarm_configuration_revision,
        confirmed_tool_catalog_revision=catalog_revision,
    )
    findings = _collect_findings(
        configuration=configuration,
        confirmed_tool_catalog=confirmed_tool_catalog,
        tool_qualification=tool_qualification,
        evaluator_qualification=evaluator_qualification,
    )
    if any(finding.severity is AlarmResolutionFindingSeverity.BLOCKING for finding in findings):
        return AlarmConfigurationResolution(
            resolution_key=resolution_key,
            status=AlarmResolutionStatus.BLOCKED,
            findings=findings,
        )
    return AlarmConfigurationResolution(
        resolution_key=resolution_key,
        status=AlarmResolutionStatus.READY,
        findings=findings,
        runtime_configuration=_materialize_runtime(
            configuration=configuration,
            resolution_key=resolution_key,
        ),
        delivery_configuration=_materialize_delivery(
            configuration=configuration,
            resolution_key=resolution_key,
            confirmed_tool_catalog=confirmed_tool_catalog,
        ),
    )


# Falla como error de programación si el input externo no ofrece el contrato mínimo esperado.
def _catalog_revision(catalog: _ConfirmedToolCatalog) -> str:
    revision = getattr(catalog, 'revision', None)
    if not isinstance(revision, str):
        raise TypeError('confirmed_tool_catalog revision must be a string')
    if not revision.strip():
        raise ValueError('confirmed_tool_catalog revision must not be empty')
    if not callable(getattr(catalog, 'get', None)):
        raise TypeError('confirmed_tool_catalog must provide get(tool_key)')
    return revision


# Recorre todo el candidato y acumula findings determinísticos; no publica Rules parciales.
def _collect_findings(
    *,
    configuration: AlarmConfiguration,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
    tool_qualification: ToolReconciliationQualification,
    evaluator_qualification: EvaluatorQualificationCatalog,
) -> tuple[AlarmResolutionFinding, ...]:
    findings: list[AlarmResolutionFinding] = []
    for rule in configuration.rules:
        findings.extend(_evaluator_findings(rule, evaluator_qualification))
        findings.extend(
            _tool_reference_findings(
                rule=rule,
                tool_key=rule.escalation.origin_tool_key,
                field_path=f'{_rule_path(rule)}.escalation.origin_tool_key',
                confirmed_tool_catalog=confirmed_tool_catalog,
                tool_qualification=tool_qualification,
            )
        )
        for step in sorted(rule.escalation.steps, key=lambda item: item.step_order):
            findings.extend(
                _tool_reference_findings(
                    rule=rule,
                    tool_key=step.target_tool_key,
                    field_path=(
                        f'{_rule_path(rule)}.escalation.steps[{step.step_order}].target_tool_key'
                    ),
                    confirmed_tool_catalog=confirmed_tool_catalog,
                    tool_qualification=tool_qualification,
                )
            )
        findings.extend(_routing_findings(rule))
        for target in rule.visual_targets:
            findings.extend(
                _visual_target_findings(
                    rule=rule,
                    target=target,
                    confirmed_tool_catalog=confirmed_tool_catalog,
                    tool_qualification=tool_qualification,
                )
            )
    return tuple(findings)


# Toda Rule definida, incluso disabled, debe usar un evaluator qualified para su family.
def _evaluator_findings(
    rule: AlarmDefinition,
    evaluator_qualification: EvaluatorQualificationCatalog,
) -> tuple[AlarmResolutionFinding, ...]:
    if evaluator_qualification.is_qualified(
        rule.identity.family_key,
        rule.evaluator_key,
    ):
        return ()
    return (
        _blocking_finding(
            code='evaluator_not_qualified',
            message=(
                f'Evaluator {rule.evaluator_key!r} is not qualified for alarm family '
                f'{rule.identity.family_key!r}'
            ),
            rule=rule,
            field_path=f'{_rule_path(rule)}.evaluator_key',
            reference_key=rule.evaluator_key,
        ),
    )


# Toda referencia Tool debe existir en el snapshot exacto y estar GREEN en reconciliation.
def _tool_reference_findings(
    *,
    rule: AlarmDefinition,
    tool_key: str,
    field_path: str,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
    tool_qualification: ToolReconciliationQualification,
) -> tuple[AlarmResolutionFinding, ...]:
    entry = confirmed_tool_catalog.get(tool_key)
    if entry is None:
        return (
            _blocking_finding(
                code='tool_reference_not_found',
                message=(
                    f'Tool reference {tool_key!r} does not exist in the confirmed Tool Catalog'
                ),
                rule=rule,
                field_path=field_path,
                reference_key=tool_key,
            ),
        )
    if tool_qualification.is_green(tool_key):
        return ()
    return (
        _blocking_finding(
            code='tool_reference_not_green',
            message=f'Tool reference {tool_key!r} is not GREEN',
            rule=rule,
            field_path=field_path,
            reference_key=tool_key,
        ),
    )


# Valida sólo la semántica B.2 por criticality; los steps disabled no forman routing ejecutable.
def _routing_findings(rule: AlarmDefinition) -> tuple[AlarmResolutionFinding, ...]:
    findings: list[AlarmResolutionFinding] = []
    enabled_steps = tuple(
        step
        for step in sorted(rule.escalation.steps, key=lambda item: item.step_order)
        if step.is_enabled
    )
    if rule.criticality is Criticality.C1:
        for step in enabled_steps:
            if step.wait_minutes_from_previous_step not in (None, 0):
                findings.append(
                    _blocking_finding(
                        code='routing_invalid_for_criticality',
                        message='C1 routing requires enabled escalation steps to be immediate',
                        rule=rule,
                        field_path=(
                            f'{_rule_path(rule)}.escalation.steps[{step.step_order}]'
                            '.wait_minutes_from_previous_step'
                        ),
                        reference_key=step.target_tool_key,
                    )
                )
        return tuple(findings)
    if rule.criticality is Criticality.C2:
        for step in enabled_steps:
            wait = step.wait_minutes_from_previous_step
            if wait is None or wait <= 0:
                findings.append(
                    _blocking_finding(
                        code='routing_invalid_for_criticality',
                        message='C2 routing requires every enabled escalation step to be delayed',
                        rule=rule,
                        field_path=(
                            f'{_rule_path(rule)}.escalation.steps[{step.step_order}]'
                            '.wait_minutes_from_previous_step'
                        ),
                        reference_key=step.target_tool_key,
                    )
                )
        return tuple(findings)
    for step in enabled_steps:
        findings.append(
            _blocking_finding(
                code='routing_invalid_for_criticality',
                message='C3 routing must not contain enabled escalation steps',
                rule=rule,
                field_path=f'{_rule_path(rule)}.escalation.steps[{step.step_order}].is_enabled',
                reference_key=step.target_tool_key,
            )
        )
    return tuple(findings)


# Resuelve referencias visuales contra ToolStructure sin copiar la estructura completa al artifact.
def _visual_target_findings(
    *,
    rule: AlarmDefinition,
    target: AlarmVisualTarget,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
    tool_qualification: ToolReconciliationQualification,
) -> tuple[AlarmResolutionFinding, ...]:
    findings = list(
        _tool_reference_findings(
            rule=rule,
            tool_key=target.tool_key,
            field_path=f'{_rule_path(rule)}.visual_targets[{target.tool_key}].tool_key',
            confirmed_tool_catalog=confirmed_tool_catalog,
            tool_qualification=tool_qualification,
        )
    )
    entry = confirmed_tool_catalog.get(target.tool_key)
    if entry is None:
        return tuple(findings)
    base_path = f'{_rule_path(rule)}.visual_targets[{target.tool_key}]'
    if entry.kind is ToolConfigurationKind.STRATEGIC:
        findings.append(
            _blocking_finding(
                code='visual_target_invalid',
                message='Alarm visual projection is not defined for Strategic tools',
                rule=rule,
                field_path=f'{base_path}.tool_key',
                reference_key=target.tool_key,
            )
        )
        return tuple(findings)
    if entry.kind is ToolConfigurationKind.PROCESS:
        if target.process_projection_mode is None:
            findings.append(
                _blocking_finding(
                    code='visual_target_invalid',
                    message='Process visual target requires process_projection_mode',
                    rule=rule,
                    field_path=f'{base_path}.process_projection_mode',
                    reference_key=target.tool_key,
                )
            )
    elif target.process_projection_mode is not None:
        findings.append(
            _blocking_finding(
                code='visual_target_invalid',
                message=(
                    'Integrated Operations visual target must not define process_projection_mode'
                ),
                rule=rule,
                field_path=f'{base_path}.process_projection_mode',
                reference_key=target.tool_key,
            )
        )
    for component_key in target.component_keys:
        try:
            entry.structure.component(component_key)
        except ToolConfigurationValidationError:
            findings.append(
                _blocking_finding(
                    code='visual_target_invalid',
                    message=f'Visual target references unknown component {component_key!r}',
                    rule=rule,
                    field_path=f'{base_path}.component_keys[{component_key}]',
                    reference_key=component_key,
                )
            )
    for subcomponent in target.subcomponents:
        try:
            component = entry.structure.component(subcomponent.owner_component_key)
            component.subcomponent(subcomponent.subcomponent_key)
        except ToolConfigurationValidationError:
            reference_key = f'{subcomponent.owner_component_key}/{subcomponent.subcomponent_key}'
            findings.append(
                _blocking_finding(
                    code='visual_target_invalid',
                    message=f'Visual target references unknown subcomponent {reference_key!r}',
                    rule=rule,
                    field_path=f'{base_path}.subcomponents[{reference_key}]',
                    reference_key=reference_key,
                )
            )
    return tuple(findings)


# Runtime conserva todas las identities definidas, pero crea PlannedAlarm sólo para Rules activas.
def _materialize_runtime(
    *,
    configuration: AlarmConfiguration,
    resolution_key: AlarmResolutionKey,
) -> RuntimeAlarmConfiguration:
    active_rules = tuple(rule for rule in configuration.rules if rule.is_active)
    planned_alarms = tuple(
        PlannedAlarm(
            identity=rule.identity,
            kind=rule.kind,
            criticality=rule.criticality,
            priority_group=rule.priority_group,
            priority_order=rule.priority_order,
            evaluator_key=rule.evaluator_key,
            alarm_configuration_revision=resolution_key.alarm_configuration_revision,
            tool_registry_revision=resolution_key.confirmed_tool_catalog_revision,
            routing=_materialize_routing(rule),
            deactivation_policy=(
                DeactivationPolicy(
                    approval_required=rule.default_deactivation.approval_required,
                )
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
    return RuntimeAlarmConfiguration(
        resolution_key=resolution_key,
        defined_alarm_identities=tuple(rule.identity for rule in configuration.rules),
        planned_alarms=planned_alarms,
        parameters_by_alarm={rule.identity: rule.parameters for rule in active_rules},
    )


# C1 usa destinos inmediatos; C2 convierte esperas relativas en offsets absolutos acumulados; C3 queda sólo en origin.
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


# Delivery conserva todas las Rules definidas, incluidas disabled y TRACE_ONLY.
def _materialize_delivery(
    *,
    configuration: AlarmConfiguration,
    resolution_key: AlarmResolutionKey,
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> DeliveryAlarmConfiguration:
    messages_by_key = {message.message_key: message for message in configuration.messages}
    return DeliveryAlarmConfiguration(
        resolution_key=resolution_key,
        alarms=tuple(
            _materialize_delivery_alarm(
                rule=rule,
                messages_by_key=messages_by_key,
                confirmed_tool_catalog=confirmed_tool_catalog,
            )
            for rule in configuration.rules
        ),
    )


# Materializa metadata de entrega sin evaluator, parameters, routing ni hot state.
def _materialize_delivery_alarm(
    *,
    rule: AlarmDefinition,
    messages_by_key: dict[str, MessageDefinition],
    confirmed_tool_catalog: _ConfirmedToolCatalog,
) -> ResolvedDeliveryAlarm:
    return ResolvedDeliveryAlarm(
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


# Un Message inactivo ya fue filtrado; un override presente reemplaza por completo la policy default.
def _materialize_message(
    *,
    message: MessageDefinition,
    default_deactivation: _DeactivationDefinition,
) -> ResolvedDeliveryMessage:
    deactivation = (
        default_deactivation
        if message.deactivation_override is None
        else message.deactivation_override
    )
    return ResolvedDeliveryMessage(
        message_key=message.message_key,
        display_text=message.display_text,
        deactivation_policy=_materialize_deactivation_policy(deactivation),
    )


# Traduce la policy authored al DTO Delivery sin modificar valores.
def _materialize_deactivation_policy(
    definition: _DeactivationDefinition,
) -> ResolvedDeactivationPolicy:
    return ResolvedDeactivationPolicy(
        enabled=definition.enabled,
        max_duration_hours=definition.max_duration_hours,
        approval_required=definition.approval_required,
    )


# El resultado mantiene referencias estables; ToolStructure sigue siendo autoridad externa.
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


# Centraliza la forma de findings BLOCKING para mantener códigos y paths consistentes.
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


# Usa identity canónica en field_path para evitar depender de la posición de la Rule en la tupla.
def _rule_path(rule: AlarmDefinition) -> str:
    return f'rules[{rule.identity.canonical_key}]'
