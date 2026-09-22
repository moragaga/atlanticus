from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmConfiguration,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmIdentity,
    AlarmKind,
    AlarmVisualTarget,
    BusinessCategory,
    Criticality,
    MessageDefinition,
    MessageScope,
    OperationalArea,
    ReappearanceDefinition,
    VisibilityMode,
)


def message(
    message_key: str = 'message-1',
    *,
    scope: MessageScope = MessageScope.GLOBAL,
    family_key: str | None = None,
    is_active: bool = True,
) -> MessageDefinition:
    return MessageDefinition(
        message_key=message_key,
        scope=scope,
        family_key=family_key,
        display_text=f'Text for {message_key}',
        is_active=is_active,
    )


def rule(
    alarm_key: str = 'alarm-1',
    *,
    family_key: str = 'family-a',
    rule_name: str | None = None,
    kind: AlarmKind = AlarmKind.IMPACT,
    priority_group: str = 'group-a',
    priority_order: int = 1,
    message_keys: tuple[str, ...] = ('message-1',),
    is_special_condition: bool = False,
    special_conditions: tuple[AlarmIdentity, ...] = (),
) -> AlarmDefinition:
    return AlarmDefinition(
        identity=AlarmIdentity(family_key=family_key, alarm_key=alarm_key),
        rule_name=rule_name or f'rule-{alarm_key}',
        display_name=f'Display {alarm_key}',
        title=f'Title {alarm_key}',
        cause_template=f'Cause {alarm_key}',
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=is_special_condition,
        kind=kind,
        criticality=Criticality.C1,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.MINE,),
        color=AlarmColor.RED,
        evaluator_key='evaluator-a',
        parameters={'threshold': 10.5, 'enabled': True, 'label': 'value'},
        priority_group=priority_group,
        priority_order=priority_order,
        message_keys=message_keys,
        reappearance=ReappearanceDefinition(
            after_minutes=5,
            special_conditions=special_conditions,
        ),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True,
            max_duration_hours=2,
            approval_required=False,
        ),
        escalation=AlarmEscalationDefinition(origin_tool_key='tool-a'),
        visual_targets=(AlarmVisualTarget(tool_key='tool-a'),),
    )


def configuration() -> AlarmConfiguration:
    return AlarmConfiguration(rules=(rule(),), messages=(message(),))
