# Espejo comentado de IDs de estructura Component -> Subcomponent.

STRUCTURE_ROOT_ID = 'ada-tool-structure-editor'
STRUCTURE_DOCUMENT_STORE_ID = 'ada-tool-structure-editor-document-store'
STRUCTURE_VALIDITY_STORE_ID = 'ada-tool-structure-editor-validity-store'
STRUCTURE_COMPONENTS_CONTAINER_ID = 'ada-tool-structure-editor-components'
STRUCTURE_ADD_COMPONENT_ID = 'ada-tool-structure-editor-add-component'
STRUCTURE_VALIDATION_MESSAGE_ID = 'ada-tool-structure-editor-validation-message'
TOOL_CONFIGURATION_EDITOR_ROOT_ID = 'ada-tool-configuration-editor-complete'

COMPONENT_ROW_TYPE = 'ada-tool-structure-component-row'
COMPONENT_KEY_TYPE = 'ada-tool-structure-component-key'
COMPONENT_DISPLAY_NAME_TYPE = 'ada-tool-structure-component-display-name'
COMPONENT_SCOPE_TYPE = 'ada-tool-structure-component-scope'
COMPONENT_SCOPE_WRAPPER_TYPE = 'ada-tool-structure-component-scope-wrapper'
COMPONENT_LAYOUT_ROLE_TYPE = 'ada-tool-structure-component-layout-role'
COMPONENT_LAYOUT_WRAPPER_TYPE = 'ada-tool-structure-component-layout-wrapper'
COMPONENT_DELETE_TYPE = 'ada-tool-structure-component-delete'
COMPONENT_ADD_SUBCOMPONENT_TYPE = 'ada-tool-structure-component-add-subcomponent'
COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE = (
    'ada-tool-structure-component-subcomponents-container'
)

SUBCOMPONENT_ROW_TYPE = 'ada-tool-structure-subcomponent-row'
SUBCOMPONENT_KEY_TYPE = 'ada-tool-structure-subcomponent-key'
SUBCOMPONENT_DISPLAY_NAME_TYPE = 'ada-tool-structure-subcomponent-display-name'
SUBCOMPONENT_LINKED_TYPE = 'ada-tool-structure-subcomponent-linked'
SUBCOMPONENT_LINKED_WRAPPER_TYPE = (
    'ada-tool-structure-subcomponent-linked-wrapper'
)
SUBCOMPONENT_DELETE_TYPE = 'ada-tool-structure-subcomponent-delete'


def row_id(row_type: str, index: int) -> dict[str, object]:
    return {'type': row_type, 'index': index}


# Los controles de nivel Component emparejan MATCH únicamente por owner_index.
def component_nested_id(
    row_type: str,
    owner_index: int,
) -> dict[str, object]:
    return {'type': row_type, 'owner_index': owner_index}


# Los Subcomponents conservan índice propio y owner_index.
def nested_row_id(
    row_type: str,
    index: int,
    owner_index: int,
) -> dict[str, object]:
    return {
        'type': row_type,
        'index': index,
        'owner_index': owner_index,
    }
