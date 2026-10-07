from __future__ import annotations

from dataclasses import dataclass

from ada.alarms.core import AlarmResolutionKey, AlarmRouting, PlannedAlarm
from ada.alarms.materialization import (
    DeliveryAlarmConfiguration,
    EngineAlarmConfiguration,
    ModelerAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedModelerAlarm,
    ResolvedVisualTarget,
)
from ada.contracts.alarms import (
    AlarmColor,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    VisibilityMode,
)
from ada.contracts.tools.enums import ToolConfigurationKind
from ada.contracts.tools.structure import ToolStructure


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


def identity(alarm_key: str = 'risk') -> AlarmIdentity:
    return AlarmIdentity(family_key='mill', alarm_key=alarm_key)


def resolution_key(
    alarm_revision: str = 'ALARMS-1',
    tool_revision: str = 'TOOLS-1',
) -> AlarmResolutionKey:
    return AlarmResolutionKey(
        alarm_configuration_revision=alarm_revision,
        confirmed_tool_catalog_revision=tool_revision,
    )


def plan(
    alarm_key: str = 'risk',
    *,
    is_special_condition: bool = False,
) -> PlannedAlarm:
    return PlannedAlarm(
        identity=identity(alarm_key),
        kind=AlarmKind.RISK,
        criticality=Criticality.C2,
        is_special_condition=is_special_condition,
        priority_group='mill-feed',
        priority_order=1,
        evaluator_key='threshold',
        alarm_configuration_revision='ALARMS-1',
        tool_registry_revision='TOOLS-1',
        routing=AlarmRouting(origin_tool_key='tool-a'),
    )


def engine_configuration(
    *,
    is_special_condition: bool = False,
) -> EngineAlarmConfiguration:
    alarm = plan(is_special_condition=is_special_condition)
    return EngineAlarmConfiguration(
        resolution_key=resolution_key(),
        defined_alarm_identities=(alarm.identity, identity('disabled')),
        planned_alarms=(alarm,),
        parameters_by_alarm={alarm.identity: {'limit': 10.0}},
    )


def modeler_alarm(alarm_key: str = 'risk') -> ResolvedModelerAlarm:
    return ResolvedModelerAlarm(
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
        priority_group='mill-feed',
        priority_order=1,
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


def modeler_configuration() -> ModelerAlarmConfiguration:
    return ModelerAlarmConfiguration(
        resolution_key=resolution_key(),
        alarms=(modeler_alarm(),),
    )


def delivery_configuration() -> DeliveryAlarmConfiguration:
    return DeliveryAlarmConfiguration(
        resolution_key=resolution_key(),
        publication_tool_keys=('tool-a',),
    )
