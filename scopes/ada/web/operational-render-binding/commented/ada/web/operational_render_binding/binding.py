from ada.web.operational_render_binding.errors import OperationalRenderBindingError
from ada.web.operational_render_binding.models import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)
from ada.web.tools.structure import ToolStructure


def bind_operational_render(structure: ToolStructure) -> OperationalRenderBinding:
    # Configuration determina existencia y orden; ningún Store participa en este paso.
    if not isinstance(structure, ToolStructure):
        raise OperationalRenderBindingError('Operational render requires ToolStructure')
    return OperationalRenderBinding(
        structure=structure,
        components=tuple(
            OperationalComponentBinding(component=component)
            for component in structure.components
        ),
    )
