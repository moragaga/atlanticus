from ada.configuration.tools import ToolStructure
from ada.web.component_store.errors import ComponentStoreValidationError
from ada.web.component_store.models import ComponentStoreSnapshot


def build_empty_component_stores(
    structure: ToolStructure,
) -> tuple[ComponentStoreSnapshot, ...]:
    # Tool Structure es la autoridad de qué Components existen.
    # Este builder no consulta datos, proveedores, Cosmos ni UI.
    if not isinstance(structure, ToolStructure):
        raise ComponentStoreValidationError('Tool Structure contract is invalid')

    # Se crea exactamente un Store por Component, conservando el orden estructural.
    # Los Subcomponents no aparecen aquí y, por lo tanto, nunca crean Stores propios.
    return tuple(
        ComponentStoreSnapshot(
            tool_key=structure.tool_key,
            component_key=component.key,
        )
        for component in structure.components
    )
