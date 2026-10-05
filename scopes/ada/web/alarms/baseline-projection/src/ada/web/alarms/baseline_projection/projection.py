from ada.contracts.tools.enums import ToolConfigurationKind
from ada.contracts.tools.structure import ToolComponent, ToolStructure
from ada.web.alarms.baseline_projection.errors import AlarmBaselineProjectionError
from ada.web.alarms.baseline_projection.models import (
    AlarmBaselineAnchorKind,
    AlarmBaselinePoint,
    AlarmBaselineProjection,
)


def project_alarm_baseline(
    structure: ToolStructure,
    *,
    bottom_component_key: str | None = None,
) -> AlarmBaselineProjection:
    if not isinstance(structure, ToolStructure):
        raise TypeError('Tool Structure is required')

    bottom_component = None
    if bottom_component_key is not None:
        if structure.kind is not ToolConfigurationKind.PROCESS:
            raise AlarmBaselineProjectionError(
                'Alarm baseline bottom component is only supported for Process'
            )
        try:
            bottom_component = structure.component(bottom_component_key)
        except ValueError as error:
            raise AlarmBaselineProjectionError(
                'Alarm baseline bottom component must reference a Tool component'
            ) from error
        if bottom_component.key == structure.center_component_key:
            raise AlarmBaselineProjectionError(
                'Alarm baseline bottom component must differ from Process center component'
            )

    main_components = tuple(
        component
        for component in structure.components
        if bottom_component is None or component.key != bottom_component.key
    )
    if not main_components:
        raise AlarmBaselineProjectionError('Alarm baseline requires main components')

    return AlarmBaselineProjection(
        tool_key=structure.tool_key,
        kind=structure.kind,
        main_points=tuple(
            _project_component(structure=structure, component=component)
            for component in main_components
        ),
        bottom_point=(
            None
            if bottom_component is None
            else _project_component(structure=structure, component=bottom_component)
        ),
    )


def _project_component(
    *,
    structure: ToolStructure,
    component: ToolComponent,
) -> AlarmBaselinePoint:
    scope = component.scope or structure.operational_scope
    if scope is None:
        raise AlarmBaselineProjectionError(
            'Alarm baseline component requires operational scope'
        )
    return AlarmBaselinePoint(
        anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
        anchor_key=component.key,
        component_key=component.key,
        display_name=component.display_name,
        scope=scope,
    )
