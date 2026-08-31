from ada.configuration.tools import ToolConfigurationKind, ToolStructure

from ada.web.body.projection.errors import ToolBodyProjectionError
from ada.web.body.projection.models import (
    ToolBodyComponentBinding,
    ToolBodyProjection,
    ToolBodySubcomponentBinding,
)


# Proyecta la topología persistida a identidades estables para la capa de composición.
def project_tool_body(structure: ToolStructure) -> ToolBodyProjection:
    if not isinstance(structure, ToolStructure):
        raise ToolBodyProjectionError('Tool body projection requires Tool Structure')
    components = tuple(
        _project_component(structure, component_index=index)
        for index in range(len(structure.components))
    )
    return ToolBodyProjection(
        tool_key=structure.tool_key,
        kind=structure.kind,
        root_id=f'ada-tool-{structure.tool_key}-body',
        components=components,
    )


def _project_component(
    structure: ToolStructure,
    *,
    component_index: int,
) -> ToolBodyComponentBinding:
    component = structure.components[component_index]
    # Process hereda un scope operacional común; IO conserva scope por componente.
    if structure.kind is ToolConfigurationKind.PROCESS:
        scope = structure.operational_scope
    else:
        scope = component.scope
    if scope is None:
        raise ToolBodyProjectionError(
            f'Tool body component scope cannot be resolved: {component.key!r}'
        )
    return ToolBodyComponentBinding(
        tool_key=structure.tool_key,
        component_key=component.key,
        display_name=component.display_name,
        scope=scope,
        layout_role=component.layout_role,
        wrapper_id=(
            f'ada-tool-{structure.tool_key}-component-{component.key}'
        ),
        subcomponents=tuple(
            ToolBodySubcomponentBinding(
                tool_key=structure.tool_key,
                owner_component_key=component.key,
                subcomponent_key=subcomponent.key,
                display_name=subcomponent.display_name,
                linked_component_keys=subcomponent.linked_component_keys,
                wrapper_id=(
                    f'ada-tool-{structure.tool_key}-subcomponent-'
                    f'{component.key}-{subcomponent.key}'
                ),
            )
            for subcomponent in component.subcomponents
        ),
    )
