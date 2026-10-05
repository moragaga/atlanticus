from ada.web.operational_render_binding.errors import OperationalRenderBindingError
from ada.web.operational_render_binding.models import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)
from ada.contracts.tools.structure import ToolStructure


def bind_operational_render(
    structure: ToolStructure,
    *,
    bottom_component_key: str | None = None,
) -> OperationalRenderBinding:
    if not isinstance(structure, ToolStructure):
        raise OperationalRenderBindingError('Operational render requires ToolStructure')
    return OperationalRenderBinding(
        structure=structure,
        components=tuple(
            OperationalComponentBinding(component=component) for component in structure.components
        ),
        bottom_component_key=bottom_component_key,
    )
