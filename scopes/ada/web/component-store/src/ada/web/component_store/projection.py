from ada.configuration.tools import ToolStructure
from ada.web.component_store.errors import ComponentStoreValidationError
from ada.web.component_store.models import ComponentStoreSnapshot


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
