from __future__ import annotations

from dataclasses import dataclass

from ada.alarms.materialization import (
    AlarmResolutionStatus,


    resolve_alarm_configuration,
)
from ada.contracts.alarms import (
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
    OperationalArea,
    ProcessAlarmProjectionMode,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent


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


def test_ready_resolution_materializes_engine_modeler_and_delivery() -> None:
    visible = rule(
        alarm_key='risk',
        visual_targets=(
            AlarmVisualTarget(
                tool_key='tool_a',
                process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
            ),
        ),
    )
    trace = rule(
        alarm_key='trace',
        visibility_mode=VisibilityMode.TRACE_ONLY,
        priority_order=2,
        visual_targets=(
            AlarmVisualTarget(
                tool_key='tool_b',
                process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
            ),
        ),
    )
    configuration = AlarmConfiguration(rules=(visible, trace), messages=())
    catalog = ConfirmedToolCatalog(
        revision='TOOLS-9',
        entries={
            'tool_a': process_entry('tool_a'),
            'tool_b': process_entry('tool_b'),
        },
    )

    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-4',
        confirmed_tool_catalog=catalog,
    )

    assert result.status is AlarmResolutionStatus.READY
    assert result.engine_configuration is not None
    assert result.modeler_configuration is not None
    assert result.delivery_configuration is not None
    assert result.engine_configuration.resolution_key == result.resolution_key
    assert result.modeler_configuration.resolution_key == result.resolution_key
    assert result.delivery_configuration.resolution_key == result.resolution_key
    assert tuple(alarm.identity.alarm_key for alarm in result.modeler_configuration.alarms) == (
        'risk',
        'trace',
    )
    assert result.delivery_configuration.publication_tool_keys == ('tool_a',)


def test_ready_resolution_propagates_special_condition_to_engine_plan() -> None:
    configuration = AlarmConfiguration(
        rules=(rule(alarm_key='special', is_special_condition=True),),
        messages=(),
    )
    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-SPECIAL',
        confirmed_tool_catalog=ConfirmedToolCatalog(
            revision='TOOLS-1',
            entries={'tool_a': process_entry('tool_a')},
        ),
    )

    assert result.status is AlarmResolutionStatus.READY
    assert result.engine_configuration is not None
    assert result.engine_configuration.planned_alarms[0].is_special_condition is True


def test_modeler_receives_priority_metadata_without_reading_engine_configuration() -> None:
    configuration = AlarmConfiguration(
        rules=(
            rule(
                alarm_key='risk',
                priority_group='mill-feed',
                priority_order=7,
            ),
        ),
        messages=(),
    )
    result = resolve_alarm_configuration(
        configuration=configuration,
        alarm_configuration_revision='ALARMS-1',
        confirmed_tool_catalog=ConfirmedToolCatalog(
            revision='TOOLS-1',
            entries={'tool_a': process_entry('tool_a')},
        ),
    )

    alarm = result.modeler_configuration.alarms[0]
    assert alarm.priority_group == 'mill-feed'
    assert alarm.priority_order == 7


def rule(
    *,
    alarm_key: str,
    visibility_mode: VisibilityMode = VisibilityMode.VISIBLE,
    is_special_condition: bool = False,
    priority_group: str = 'mill-feed',
    priority_order: int = 1,
    visual_targets: tuple[AlarmVisualTarget, ...] = (),
) -> AlarmDefinition:
    return AlarmDefinition(
        identity=AlarmIdentity(family_key='mill', alarm_key=alarm_key),
        rule_name=f'{alarm_key}-rule',
        display_name=alarm_key.title(),
        title=f'{alarm_key.title()} alarm',
        cause_template='Value exceeds threshold',
        is_active=True,
        visibility_mode=visibility_mode,
        is_special_condition=is_special_condition,
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.PLANT,),
        color=AlarmColor.YELLOW,
        evaluator_key='threshold',
        parameters={'limit': 10.0},
        priority_group=priority_group,
        priority_order=priority_order,
        message_keys=(),
        reappearance=ReappearanceDefinition(),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True,
            max_duration_hours=4,
            approval_required=True,
        ),
        escalation=AlarmEscalationDefinition(origin_tool_key='tool_a'),
        visual_targets=visual_targets,
    )


def process_entry(tool_key: str) -> CatalogEntry:
    structure = ToolStructure(
        tool_key=tool_key,
        kind=ToolConfigurationKind.PROCESS,
        components=(
            ToolComponent(
                key='main',
                display_name='Main',
                subcomponents=(ToolSubcomponent(key='pressure', display_name='Pressure'),),
            ),
        ),
        operational_scope=ToolScope.PLANT,
        center_component_key='main',
    )
    return CatalogEntry(kind=ToolConfigurationKind.PROCESS, structure=structure)
