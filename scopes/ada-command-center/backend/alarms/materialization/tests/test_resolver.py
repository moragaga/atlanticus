from __future__ import annotations

from dataclasses import dataclass

import pytest

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.alarms.materialization import (
    AlarmResolutionStatus,
    EvaluatorQualificationCatalog,
    EvaluatorQualificationKey,
    ToolReconciliationQualification,
    resolve_alarm_configuration,
)
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmConfiguration,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    AlarmIdentity,
    AlarmKind,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
    BusinessCategory,
    Criticality,
    MessageDeactivationDefinition,
    MessageDefinition,
    MessageScope,
    OperationalArea,
    ProcessAlarmProjectionMode,
    ReappearanceDefinition,
    VisibilityMode,
)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    kind: ToolConfigurationKind
    structure: ToolStructure


@dataclass(frozen=True, slots=True)
class ConfirmedToolCatalog:
    revision: str
    entries: dict[str, CatalogEntry]

    def get(self, tool_key: str) -> CatalogEntry | None:
        return self.entries.get(tool_key)


def test_ready_resolution_materializes_runtime_and_delivery_atomically() -> None:
    special_identity = AlarmIdentity(family_key='mill', alarm_key='special')
    configuration = AlarmConfiguration(
        rules=(
            rule(
                alarm_key='risk',
                criticality=Criticality.C2,
                message_keys=('default', 'inactive', 'override'),
                reappearance=ReappearanceDefinition(
                    after_minutes=15,
                    special_conditions=(special_identity,),
                ),
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='tool_a',
                    steps=(
                        AlarmEscalationStepDefinition(
                            step_order=2,
                            target_tool_key='tool_c',
                            is_enabled=True,
                            wait_minutes_from_previous_step=5,
                        ),
                        AlarmEscalationStepDefinition(
                            step_order=1,
                            target_tool_key='tool_b',
                            is_enabled=True,
                            wait_minutes_from_previous_step=10,
                        ),
                    ),
                ),
                visual_targets=(
                    AlarmVisualTarget(
                        tool_key='tool_a',
                        component_keys=('main',),
                        subcomponents=(
                            AlarmVisualSubcomponentTarget(
                                owner_component_key='main',
                                subcomponent_key='pressure',
                            ),
                        ),
                        process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
                    ),
                ),
            ),
            rule(
                alarm_key='special',
                is_active=False,
                is_special_condition=True,
                priority_order=2,
                criticality=Criticality.C3,
            ),
        ),
        messages=(
            message('default'),
            message('inactive', is_active=False),
            message(
                'override',
                override=MessageDeactivationDefinition(
                    enabled=False,
                    max_duration_hours=None,
                    approval_required=False,
                ),
            ),
        ),
    )
    catalog = tool_catalog('tool_a', 'tool_b', 'tool_c', revision='TOOLS-9')

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-4',
        confirmed_tool_catalog=catalog,
        tool_qualification=green_qualification('tool_a', 'tool_b', 'tool_c'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.READY
    assert result.findings == ()
    assert result.resolution_key.alarm_configuration_revision == 'ALARMS-4'
    assert result.resolution_key.confirmed_tool_catalog_revision == 'TOOLS-9'
    assert result.runtime_configuration is not None
    assert result.delivery_configuration is not None
    runtime = result.runtime_configuration
    assert runtime.defined_alarm_identities == (
        AlarmIdentity('mill', 'risk'),
        AlarmIdentity('mill', 'special'),
    )
    assert len(runtime.planned_alarms) == 1
    plan = runtime.planned_alarms[0]
    assert plan.identity == AlarmIdentity('mill', 'risk')
    assert plan.reappearance_after_seconds == 900
    assert plan.reappearance_special_conditions == (special_identity,)
    assert tuple(
        (destination.tool_key, destination.delay_seconds)
        for destination in plan.routing.destinations
    ) == (('tool_b', 600), ('tool_c', 900))
    assert set(runtime.parameters_by_alarm) == {AlarmIdentity('mill', 'risk')}
    delivery = result.delivery_configuration
    assert tuple(alarm.identity.alarm_key for alarm in delivery.alarms) == ('risk', 'special')
    risk_delivery = delivery.alarms[0]
    assert tuple(item.message_key for item in risk_delivery.messages) == ('default', 'override')
    assert risk_delivery.messages[0].deactivation_policy.enabled is True
    assert risk_delivery.messages[0].deactivation_policy.max_duration_hours == 4
    assert risk_delivery.messages[1].deactivation_policy.enabled is False
    assert risk_delivery.messages[1].deactivation_policy.max_duration_hours is None
    assert risk_delivery.visual_targets[0].tool_kind is ToolConfigurationKind.PROCESS


def test_disabled_rule_still_requires_evaluator_qualification() -> None:
    configuration = AlarmConfiguration(
        rules=(rule(is_active=False, evaluator_key='missing'),),
        messages=(),
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=tool_catalog('tool_a'),
        tool_qualification=green_qualification('tool_a'),
        evaluator_qualification=EvaluatorQualificationCatalog(qualified_keys=()),
    )

    assert result.status is AlarmResolutionStatus.BLOCKED
    assert result.runtime_configuration is None
    assert result.delivery_configuration is None
    assert tuple(finding.code for finding in result.findings) == ('evaluator_not_qualified',)
    assert result.findings[0].field_path == 'rules[mill/risk].evaluator_key'


def test_all_defined_tool_references_require_catalog_presence_and_green() -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='tool_a',
                    steps=(
                        AlarmEscalationStepDefinition(
                            step_order=1,
                            target_tool_key='missing-tool',
                            is_enabled=False,
                            wait_minutes_from_previous_step=99,
                        ),
                    ),
                ),
                visual_targets=(
                    AlarmVisualTarget(
                        tool_key='tool_b',
                        process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
                    ),
                ),
            ),
        ),
        messages=(),
    )
    catalog = tool_catalog('tool_a', 'tool_b')

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=catalog,
        tool_qualification=green_qualification('tool_a'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == (
        'tool_reference_not_found',
        'tool_reference_not_green',
    )
    assert result.findings[0].field_path.endswith('steps[1].target_tool_key')
    assert result.findings[1].field_path.endswith('visual_targets[tool_b].tool_key')


@pytest.mark.parametrize(
    ('criticality', 'wait_minutes', 'enabled', 'field_suffix'),
    (
        (Criticality.C1, 5, True, 'wait_minutes_from_previous_step'),
        (Criticality.C2, None, True, 'wait_minutes_from_previous_step'),
        (Criticality.C2, 0, True, 'wait_minutes_from_previous_step'),
        (Criticality.C3, None, True, 'is_enabled'),
    ),
)
def test_invalid_routing_for_criticality_blocks_candidate(
    criticality: Criticality,
    wait_minutes: int | None,
    enabled: bool,
    field_suffix: str,
) -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                criticality=criticality,
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='tool_a',
                    steps=(
                        AlarmEscalationStepDefinition(
                            step_order=1,
                            target_tool_key='tool_b',
                            is_enabled=enabled,
                            wait_minutes_from_previous_step=wait_minutes,
                        ),
                    ),
                ),
            ),
        ),
        messages=(),
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=tool_catalog('tool_a', 'tool_b'),
        tool_qualification=green_qualification('tool_a', 'tool_b'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == (
        'routing_invalid_for_criticality',
    )
    assert result.findings[0].field_path is not None
    assert result.findings[0].field_path.endswith(field_suffix)


def test_c2_disabled_steps_do_not_contribute_to_executable_delay() -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                criticality=Criticality.C2,
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='tool_a',
                    steps=(
                        AlarmEscalationStepDefinition(1, 'tool_b', True, 10),
                        AlarmEscalationStepDefinition(2, 'tool_c', False, 99),
                        AlarmEscalationStepDefinition(3, 'tool_d', True, 5),
                    ),
                ),
            ),
        ),
        messages=(),
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=tool_catalog('tool_a', 'tool_b', 'tool_c', 'tool_d'),
        tool_qualification=green_qualification('tool_a', 'tool_b', 'tool_c', 'tool_d'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.READY
    assert result.runtime_configuration is not None
    destinations = result.runtime_configuration.planned_alarms[0].routing.destinations
    assert tuple((item.tool_key, item.delay_seconds) for item in destinations) == (
        ('tool_b', 600),
        ('tool_d', 900),
    )


def test_process_visual_target_reports_projection_and_structure_errors() -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                visual_targets=(
                    AlarmVisualTarget(
                        tool_key='tool_a',
                        component_keys=('missing-component',),
                        subcomponents=(
                            AlarmVisualSubcomponentTarget('main', 'missing-subcomponent'),
                        ),
                    ),
                ),
            ),
        ),
        messages=(),
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=tool_catalog('tool_a'),
        tool_qualification=green_qualification('tool_a'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == (
        'visual_target_invalid',
        'visual_target_invalid',
        'visual_target_invalid',
    )
    assert result.findings[0].field_path is not None
    assert result.findings[0].field_path.endswith('process_projection_mode')


def test_strategic_visual_target_is_blocked_while_projection_is_undefined() -> None:
    configuration = AlarmConfiguration(
        rules=(rule(visual_targets=(AlarmVisualTarget(tool_key='strategic'),)),),
        messages=(),
    )
    catalog = ConfirmedToolCatalog(
        revision='TOOLS-1',
        entries={
            'tool_a': catalog_entry('tool_a', ToolConfigurationKind.PROCESS),
            'strategic': catalog_entry('strategic', ToolConfigurationKind.STRATEGIC),
        },
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=catalog,
        tool_qualification=green_qualification('tool_a', 'strategic'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == ('visual_target_invalid',)
    assert 'Strategic' in result.findings[0].message


def test_integrated_operations_visual_target_rejects_process_projection_mode() -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                visual_targets=(
                    AlarmVisualTarget(
                        tool_key='io',
                        process_projection_mode=ProcessAlarmProjectionMode.DISTRIBUTED,
                    ),
                ),
            ),
        ),
        messages=(),
    )
    catalog = ConfirmedToolCatalog(
        revision='TOOLS-1',
        entries={
            'tool_a': catalog_entry('tool_a', ToolConfigurationKind.PROCESS),
            'io': catalog_entry('io', ToolConfigurationKind.INTEGRATED_OPERATIONS),
        },
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=catalog,
        tool_qualification=green_qualification('tool_a', 'io'),
        evaluator_qualification=evaluator_qualification(),
    )

    assert result.status is AlarmResolutionStatus.BLOCKED
    assert tuple(finding.code for finding in result.findings) == ('visual_target_invalid',)


def test_findings_are_deterministic_for_the_same_candidate() -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                evaluator_key='missing',
                escalation=AlarmEscalationDefinition(
                    origin_tool_key='missing-origin',
                    steps=(AlarmEscalationStepDefinition(2, 'missing-target', True, 5),),
                ),
            ),
        ),
        messages=(),
    )
    kwargs = dict(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=tool_catalog(),
        tool_qualification=green_qualification(),
        evaluator_qualification=EvaluatorQualificationCatalog(qualified_keys=()),
    )

    first = resolve_alarm_configuration(**kwargs)
    second = resolve_alarm_configuration(**kwargs)

    assert first == second
    assert tuple(finding.code for finding in first.findings) == (
        'evaluator_not_qualified',
        'tool_reference_not_found',
        'tool_reference_not_found',
        'routing_invalid_for_criticality',
    )


def rule(
    *,
    alarm_key: str = 'risk',
    is_active: bool = True,
    is_special_condition: bool = False,
    evaluator_key: str = 'threshold',
    priority_order: int = 1,
    criticality: Criticality = Criticality.C1,
    message_keys: tuple[str, ...] = (),
    reappearance: ReappearanceDefinition | None = None,
    escalation: AlarmEscalationDefinition | None = None,
    visual_targets: tuple[AlarmVisualTarget, ...] = (),
) -> AlarmDefinition:
    return AlarmDefinition(
        identity=AlarmIdentity(family_key='mill', alarm_key=alarm_key),
        rule_name=f'{alarm_key}-rule',
        display_name=alarm_key.title(),
        title=f'{alarm_key.title()} alarm',
        cause_template='Value exceeds threshold',
        is_active=is_active,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=is_special_condition,
        kind=AlarmKind.RISK,
        criticality=criticality,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.YELLOW,
        evaluator_key=evaluator_key,
        parameters={'limit': 10.0},
        priority_group='mill-feed',
        priority_order=priority_order,
        message_keys=message_keys,
        reappearance=reappearance or ReappearanceDefinition(),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True,
            max_duration_hours=4,
            approval_required=True,
        ),
        escalation=escalation or AlarmEscalationDefinition(origin_tool_key='tool_a'),
        visual_targets=visual_targets,
    )


def message(
    message_key: str,
    *,
    is_active: bool = True,
    override: MessageDeactivationDefinition | None = None,
) -> MessageDefinition:
    return MessageDefinition(
        message_key=message_key,
        scope=MessageScope.GLOBAL,
        display_text=f'Message {message_key}',
        is_active=is_active,
        deactivation_override=override,
    )


def evaluator_qualification() -> EvaluatorQualificationCatalog:
    return EvaluatorQualificationCatalog(
        qualified_keys=(EvaluatorQualificationKey('mill', 'threshold'),),
    )


def green_qualification(*tool_keys: str) -> ToolReconciliationQualification:
    return ToolReconciliationQualification(green_tool_keys=tuple(tool_keys))


def tool_catalog(*tool_keys: str, revision: str = 'TOOLS-1') -> ConfirmedToolCatalog:
    return ConfirmedToolCatalog(
        revision=revision,
        entries={
            tool_key: catalog_entry(tool_key, ToolConfigurationKind.PROCESS)
            for tool_key in tool_keys
        },
    )


def catalog_entry(tool_key: str, kind: ToolConfigurationKind) -> CatalogEntry:
    if kind is ToolConfigurationKind.PROCESS:
        component = ToolComponent(
            key='main',
            display_name='Main',
            subcomponents=(ToolSubcomponent(key='pressure', display_name='Pressure'),),
        )
        structure = ToolStructure(
            tool_key=tool_key,
            kind=kind,
            components=(component,),
            operational_scope=ToolScope.PLANT,
        )
    elif kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        component = ToolComponent(
            key='main',
            display_name='Main',
            subcomponents=(ToolSubcomponent(key='pressure', display_name='Pressure'),),
            scope=ToolScope.PLANT,
        )
        structure = ToolStructure(
            tool_key=tool_key,
            kind=kind,
            components=(component,),
        )
    else:
        structure = ToolStructure(
            tool_key=tool_key,
            kind=kind,
            components=(ToolComponent(key='main', display_name='Main'),),
        )
    return CatalogEntry(kind=kind, structure=structure)
