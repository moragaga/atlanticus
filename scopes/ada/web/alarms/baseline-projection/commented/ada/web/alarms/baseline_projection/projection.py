# Proyecta la topología validada de una Tool hacia los puntos contractuales del baseline.
from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolConfigurationKind,
    ToolStructure,
)
from ada.web.alarms.baseline_projection.models import (
    AlarmBaselineAnchorKind,
    AlarmBaselinePoint,
    AlarmBaselineProjection,
)


def project_alarm_baseline(structure: ToolStructure) -> AlarmBaselineProjection:
    if not isinstance(structure, ToolStructure):
        raise TypeError('Tool Structure is required')
    if structure.kind is ToolConfigurationKind.PROCESS:
        center = structure.component_for_layout_role(ProcessLayoutRole.CENTER)
        return AlarmBaselineProjection(
            tool_key=structure.tool_key,
            kind=structure.kind,
            points=(
                AlarmBaselinePoint(
                    anchor_kind=AlarmBaselineAnchorKind.LAYOUT_ROLE,
                    anchor_key=ProcessLayoutRole.CENTER.value,
                    component_key=center.key,
                    display_name=center.display_name,
                    scope=structure.operational_scope,
                ),
            ),
        )
    return AlarmBaselineProjection(
        tool_key=structure.tool_key,
        kind=structure.kind,
        points=tuple(
            AlarmBaselinePoint(
                anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
                anchor_key=component.key,
                component_key=component.key,
                display_name=component.display_name,
                scope=component.scope,
            )
            for component in structure.components
        ),
    )
