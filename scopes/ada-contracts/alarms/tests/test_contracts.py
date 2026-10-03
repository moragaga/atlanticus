import pytest

from ada.contracts.alarms import (
    AlarmColor,
    AlarmConfiguration,
    AlarmConfigurationSnapshot,
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
from ada.contracts.alarms.errors import AlarmConfigurationValidationError
from ada.contracts.tools import (
    ToolComponent,
    ToolConfigurationKind,
    ToolDependencyEntry,
    ToolDependencyManifest,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)


def _snapshot():
    identity = AlarmIdentity('crusher', 'high_temperature')
    message = MessageDefinition(
        message_key='operator_action',
        scope=MessageScope.FAMILY,
        family_key='crusher',
        display_text='Check bearing temperature',
        is_active=True,
        deactivation_override=MessageDeactivationDefinition(
            enabled=True, max_duration_hours=2, approval_required=False
        ),
    )
    rule = AlarmDefinition(
        identity=identity,
        rule_name='high_temperature_rule',
        display_name='High temperature',
        title='High temperature',
        cause_template='Bearing temperature above threshold',
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=False,
        kind=AlarmKind.IMPACT,
        criticality=Criticality.C2,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.RED,
        evaluator_key='threshold',
        parameters={'threshold': 80.0, 'enabled': True, 'tag': 'bearing'},
        priority_group='crusher_temperature',
        priority_order=1,
        message_keys=('operator_action',),
        reappearance=ReappearanceDefinition(after_minutes=10),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True, max_duration_hours=4, approval_required=True
        ),
        escalation=AlarmEscalationDefinition(
            origin_tool_key='crusher',
            steps=(
                AlarmEscalationStepDefinition(
                    step_order=1,
                    target_tool_key='integrated_operations',
                    is_enabled=True,
                    wait_minutes_from_previous_step=5,
                ),
            ),
        ),
        visual_targets=(
            AlarmVisualTarget(
                tool_key='crusher',
                component_keys=('main',),
                subcomponents=(
                    AlarmVisualSubcomponentTarget('main', 'motor'),
                ),
                process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
            ),
        ),
    )
    configuration = AlarmConfiguration(rules=(rule,), messages=(message,))
    structure = ToolStructure(
        tool_key='crusher',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            ToolComponent(
                key='main',
                display_name='Main',
                subcomponents=(ToolSubcomponent(key='motor', display_name='Motor'),),
            ),
        ),
    )
    manifest = ToolDependencyManifest(
        confirmed_tool_catalog_revision='tools-1',
        tools=(
            ToolDependencyEntry(
                tool_key='crusher',
                display_name='Crusher',
                source_release_id='release-1',
                kind=ToolConfigurationKind.PROCESS,
                structure=structure,
            ),
        ),
    )
    return AlarmConfigurationSnapshot(configuration, manifest)


def test_alarm_configuration_snapshot_roundtrip_preserves_document_contract():
    snapshot = _snapshot()
    document = snapshot.to_document()

    restored = AlarmConfigurationSnapshot.from_document(document)

    assert restored.to_document() == document
    assert restored.confirmed_tool_catalog_revision == 'tools-1'
    assert document['configuration']['rules'][0]['kind'] == 'IMPACT'
    assert document['configuration']['rules'][0]['criticality'] == 'C2'
    assert document['configuration']['rules'][0]['parameters']['threshold'] == 80.0


def test_priority_contract_rejects_duplicate_order_within_group():
    snapshot = _snapshot()
    impact = snapshot.configuration.rules[0]
    risk = AlarmDefinition(
        identity=AlarmIdentity('crusher', 'risk'),
        rule_name='risk_rule',
        display_name='Risk',
        title='Risk',
        cause_template='Risk cause',
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=False,
        kind=AlarmKind.RISK,
        criticality=Criticality.C2,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.YELLOW,
        evaluator_key='threshold',
        parameters={'threshold': 70.0},
        priority_group='crusher_temperature',
        priority_order=1,
        message_keys=(),
        reappearance=ReappearanceDefinition(after_minutes=10),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True, max_duration_hours=4, approval_required=True
        ),
        escalation=AlarmEscalationDefinition(origin_tool_key='crusher'),
        visual_targets=(),
    )

    with pytest.raises(AlarmConfigurationValidationError):
        AlarmConfiguration(rules=(impact, risk), messages=snapshot.configuration.messages)


def test_family_message_cannot_be_referenced_from_another_family():
    snapshot = _snapshot()
    rule = snapshot.configuration.rules[0]
    other_family_rule = AlarmDefinition(
        identity=AlarmIdentity('mill', 'high_temperature'),
        rule_name='mill_high_temperature',
        display_name='Mill high temperature',
        title='Mill high temperature',
        cause_template='Temperature above threshold',
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=False,
        kind=AlarmKind.IMPACT,
        criticality=Criticality.C2,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.RED,
        evaluator_key='threshold',
        parameters={'threshold': 80.0},
        priority_group='mill_temperature',
        priority_order=1,
        message_keys=('operator_action',),
        reappearance=ReappearanceDefinition(after_minutes=10),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True, max_duration_hours=4, approval_required=True
        ),
        escalation=AlarmEscalationDefinition(origin_tool_key='mill'),
        visual_targets=(),
    )

    with pytest.raises(AlarmConfigurationValidationError):
        AlarmConfiguration(
            rules=(rule, other_family_rule),
            messages=snapshot.configuration.messages,
        )
