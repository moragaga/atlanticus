from ada.web.components.errors import ComponentStoreValidationError
from ada.web.components.models import ComponentStoreSnapshot
from ada.web.tools.structure import ToolStructure


def build_empty_component_stores(
    structure: ToolStructure,
) -> tuple[ComponentStoreSnapshot, ...]:
    if not isinstance(structure, ToolStructure):
        raise ComponentStoreValidationError('Tool Structure contract is invalid')
    return tuple(
        ComponentStoreSnapshot(
            tool_key=structure.tool_key,
            component_key=component.key,
        )
        for component in structure.components
    )
