from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    PlannedAlarm,
)
from ada_command_center.alarms.materialization import (
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryAlarm,
    ResolvedVisualTarget,
    RuntimeAlarmConfiguration,
)
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    VisibilityMode,
)


def identity(alarm_key: str = 'risk') -> AlarmIdentity:
    return AlarmIdentity(family_key='mill', alarm_key=alarm_key)


def resolution_key(
    alarm_revision: str = 'R42',
    tool_revision: str = 'T18',
) -> AlarmResolutionKey:
    return AlarmResolutionKey(
        alarm_configuration_revision=alarm_revision,
        confirmed_tool_catalog_revision=tool_revision,
    )


def plan(alarm_key: str = 'risk') -> PlannedAlarm:
    return PlannedAlarm(
        identity=identity(alarm_key),
        kind=AlarmKind.RISK,
        criticality=Criticality.C2,
        priority_group='mill-feed',
        priority_order=1,
        evaluator_key='threshold',
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        routing=AlarmRouting(origin_tool_key='tool-a'),
    )


def runtime_configuration() -> RuntimeAlarmConfiguration:
    alarm = plan()
    return RuntimeAlarmConfiguration(
        resolution_key=resolution_key(),
        defined_alarm_identities=(alarm.identity, identity('disabled')),
        planned_alarms=(alarm,),
        parameters_by_alarm={alarm.identity: {'limit': 10.0}},
    )


def delivery_alarm(alarm_key: str = 'risk') -> ResolvedDeliveryAlarm:
    return ResolvedDeliveryAlarm(
        identity=identity(alarm_key),
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        display_name='Risk',
        title='Risk alarm',
        cause_template='Value {value} exceeds limit',
        kind=AlarmKind.RISK,
        criticality=Criticality.C2,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.YELLOW,
        default_deactivation_policy=ResolvedDeactivationPolicy(
            enabled=True,
            max_duration_hours=4,
            approval_required=True,
        ),
        visual_targets=(
            ResolvedVisualTarget(
                tool_key='tool-a',
                tool_kind=ToolConfigurationKind.PROCESS,
            ),
        ),
    )


def delivery_configuration() -> DeliveryAlarmConfiguration:
    return DeliveryAlarmConfiguration(
        resolution_key=resolution_key(),
        alarms=(delivery_alarm(),),
    )
