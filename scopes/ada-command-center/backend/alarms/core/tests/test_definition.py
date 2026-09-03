from types import MappingProxyType

import pytest

from ada_command_center.alarms.core import (
    AlarmColor,
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


def definition(**overrides: object) -> AlarmDefinition:
    values: dict[str, object] = {
        'identity': AlarmIdentity('sag', 'high-pressure'),
        'rule_name': 'high_pressure',
        'display_name': 'Alta presión',
        'title': 'Alta presión descarga SAG',
        'cause_template': 'Presión {pressure} supera el límite {limit}',
        'is_active': True,
        'visibility_mode': VisibilityMode.VISIBLE,
        'is_special_condition': False,
        'kind': AlarmKind.RISK,
        'criticality': Criticality.C2,
        'business_category': BusinessCategory.PRODUCTIVITY,
        'operational_areas': (OperationalArea.PLANT,),
        'color': AlarmColor.YELLOW,
        'evaluator_key': 'threshold',
        'parameters': {'limit': 10.0, 'mode': 'primary', 'enabled': True},
        'priority_group': 'sag-pressure',
        'priority_order': 2,
        'message_keys': ('GLOBAL_ACK', 'SAG_CHECK_PRESSURE'),
        'reappearance': ReappearanceDefinition(
            after_minutes=20,
            special_conditions=(AlarmIdentity('sag', 'feed-loss'),),
        ),
        'default_deactivation': AlarmDeactivationDefinition(
            enabled=True,
            max_duration_hours=2,
            approval_required=False,
        ),
        'escalation': AlarmEscalationDefinition(
            origin_tool_key='process-sag',
            steps=(
                AlarmEscalationStepDefinition(
                    step_order=1,
                    target_tool_key='integrated-operations',
                    is_enabled=True,
                    wait_minutes_from_previous_step=15,
                ),
            ),
        ),
        'visual_targets': (
            AlarmVisualTarget(
                tool_key='process-sag',
                component_keys=('central',),
                process_projection_mode=ProcessAlarmProjectionMode.DISTRIBUTED,
            ),
        ),
    }
    values.update(overrides)
    return AlarmDefinition(**values)


def test_definition_keeps_source_contract_dimensions_explicit() -> None:
    value = definition()
    assert value.identity.canonical_key == 'sag/high-pressure'
    assert value.business_category is BusinessCategory.PRODUCTIVITY
    assert value.operational_areas == (OperationalArea.PLANT,)
    assert value.color is AlarmColor.YELLOW
    assert value.visual_targets[0].process_projection_mode is (
        ProcessAlarmProjectionMode.DISTRIBUTED
    )
    assert isinstance(value.parameters, MappingProxyType)


def test_business_categories_are_frozen_to_product_catalog() -> None:
    assert {value.value for value in BusinessCategory} == {
        'ECOLOGY',
        'PRODUCTIVITY',
        'SAFETY_HEALTH',
        'COSTS',
    }


def test_alarm_colors_are_frozen_to_red_and_yellow() -> None:
    assert {value.value for value in AlarmColor} == {'RED', 'YELLOW'}


def test_definition_requires_at_least_one_operational_area() -> None:
    with pytest.raises(ValueError, match='operational_areas must not be empty'):
        definition(operational_areas=())


def test_definition_rejects_duplicate_operational_areas() -> None:
    with pytest.raises(ValueError, match='operational_areas must not contain duplicates'):
        definition(operational_areas=(OperationalArea.MINE, OperationalArea.MINE))


@pytest.mark.parametrize('invalid', [1, None, [], {'nested': True}])
def test_definition_parameters_reject_non_static_values(invalid: object) -> None:
    with pytest.raises(TypeError, match='TEXT, FLOAT, or BOOLEAN'):
        definition(parameters={'invalid': invalid})


def test_definition_parameters_are_immutable_snapshot() -> None:
    source = {'limit': 10.0}
    value = definition(parameters=source)
    source['limit'] = 20.0
    assert value.parameters['limit'] == 10.0
    with pytest.raises(TypeError):
        value.parameters['limit'] = 30.0


def test_reappearance_accepts_time_or_special_conditions() -> None:
    assert ReappearanceDefinition().after_minutes is None
    assert ReappearanceDefinition(after_minutes=20).after_minutes == 20
    special = AlarmIdentity('sag', 'feed-loss')
    assert ReappearanceDefinition(special_conditions=(special,)).special_conditions == (special,)


def test_reappearance_rejects_non_positive_time_and_duplicate_conditions() -> None:
    with pytest.raises(ValueError, match='after_minutes'):
        ReappearanceDefinition(after_minutes=0)
    special = AlarmIdentity('sag', 'feed-loss')
    with pytest.raises(ValueError, match='special_conditions'):
        ReappearanceDefinition(special_conditions=(special, special))


def test_deactivation_disabled_shape_is_strict() -> None:
    assert AlarmDeactivationDefinition(False, None, False).enabled is False
    with pytest.raises(ValueError, match='max_duration_hours'):
        AlarmDeactivationDefinition(False, 1, False)
    with pytest.raises(ValueError, match='approval'):
        AlarmDeactivationDefinition(False, None, True)


@pytest.mark.parametrize('hours', [1, 12])
def test_deactivation_accepts_configured_shift_range(hours: int) -> None:
    value = AlarmDeactivationDefinition(True, hours, False)
    assert value.max_duration_hours == hours


@pytest.mark.parametrize('hours', [0, 13])
def test_deactivation_rejects_duration_outside_shift_range(hours: int) -> None:
    with pytest.raises(ValueError, match='between 1 and 12'):
        AlarmDeactivationDefinition(True, hours, False)


def test_message_scope_is_locally_coherent() -> None:
    global_message = MessageDefinition(
        message_key='GLOBAL_ACK',
        scope=MessageScope.GLOBAL,
        display_text='Reconocer',
        is_active=True,
    )
    assert global_message.family_key is None
    family_message = MessageDefinition(
        message_key='SAG_CHECK',
        scope=MessageScope.FAMILY,
        family_key='sag',
        display_text='Revisar SAG',
        is_active=True,
    )
    assert family_message.family_key == 'sag'


def test_message_scope_rejects_cross_shape_family_key() -> None:
    with pytest.raises(ValueError, match='GLOBAL'):
        MessageDefinition(
            message_key='GLOBAL_ACK',
            scope=MessageScope.GLOBAL,
            family_key='sag',
            display_text='Reconocer',
            is_active=True,
        )
    with pytest.raises((TypeError, ValueError), match='family_key'):
        MessageDefinition(
            message_key='SAG_CHECK',
            scope=MessageScope.FAMILY,
            display_text='Revisar SAG',
            is_active=True,
        )


def test_message_deactivation_override_is_a_complete_contract() -> None:
    override = MessageDeactivationDefinition(
        enabled=True,
        max_duration_hours=7,
        approval_required=True,
    )
    message = MessageDefinition(
        message_key='SAG_CONTROLLED',
        scope=MessageScope.FAMILY,
        family_key='sag',
        display_text='Condición controlada',
        is_active=True,
        deactivation_override=override,
    )
    assert message.deactivation_override is override


def test_escalation_rejects_duplicate_orders_targets_and_origin_target() -> None:
    with pytest.raises(ValueError, match='step_order'):
        AlarmEscalationDefinition(
            origin_tool_key='process-sag',
            steps=(
                AlarmEscalationStepDefinition(1, 'tool-b', True, 10),
                AlarmEscalationStepDefinition(1, 'tool-c', False, None),
            ),
        )
    with pytest.raises(ValueError, match='targets'):
        AlarmEscalationDefinition(
            origin_tool_key='process-sag',
            steps=(
                AlarmEscalationStepDefinition(1, 'tool-b', True, 10),
                AlarmEscalationStepDefinition(2, 'tool-b', False, None),
            ),
        )
    with pytest.raises(ValueError, match='targets'):
        AlarmEscalationDefinition(
            origin_tool_key='process-sag',
            steps=(AlarmEscalationStepDefinition(1, 'process-sag', True, 0),),
        )


def test_visual_target_allows_empty_local_projection_shape() -> None:
    value = AlarmVisualTarget(tool_key='strategic-a')
    assert value.component_keys == ()
    assert value.subcomponents == ()
    assert value.process_projection_mode is None


def test_visual_target_rejects_duplicate_components_and_subcomponents() -> None:
    with pytest.raises(ValueError, match='component_keys'):
        AlarmVisualTarget(tool_key='tool-a', component_keys=('c1', 'c1'))
    sub = AlarmVisualSubcomponentTarget('c1', 's1')
    with pytest.raises(ValueError, match='subcomponents'):
        AlarmVisualTarget(tool_key='tool-a', subcomponents=(sub, sub))


def test_definition_rejects_duplicate_tool_targets_and_message_keys() -> None:
    target = AlarmVisualTarget(tool_key='tool-a')
    with pytest.raises(ValueError, match='visual_targets'):
        definition(visual_targets=(target, target))
    with pytest.raises(ValueError, match='message_keys'):
        definition(message_keys=('M1', 'M1'))


def test_process_projection_mode_is_only_local_shape_in_b1() -> None:
    generic = AlarmVisualTarget(
        tool_key='process-a',
        process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
    )
    distributed = AlarmVisualTarget(
        tool_key='process-b',
        process_projection_mode=ProcessAlarmProjectionMode.DISTRIBUTED,
    )
    assert generic.process_projection_mode is ProcessAlarmProjectionMode.GENERIC
    assert distributed.process_projection_mode is ProcessAlarmProjectionMode.DISTRIBUTED
