STRUCTURE_ROOT_ID = 'ada-tool-structure-editor'
STRUCTURE_DOCUMENT_STORE_ID = 'ada-tool-structure-editor-document-store'
STRUCTURE_VALIDITY_STORE_ID = 'ada-tool-structure-editor-validity-store'
STRUCTURE_KIND_STORE_ID = 'ada-tool-structure-editor-kind-store'
STRUCTURE_COMPONENTS_CONTAINER_ID = 'ada-tool-structure-editor-components'
STRUCTURE_ADD_COMPONENT_ID = 'ada-tool-structure-editor-add-component'
STRUCTURE_VALIDATION_MESSAGE_ID = 'ada-tool-structure-editor-validation-message'
TOOL_CONFIGURATION_EDITOR_ROOT_ID = 'ada-tool-configuration-editor-complete'

COMPONENT_ROW_TYPE = 'ada-tool-structure-component-row'
COMPONENT_KEY_TYPE = 'ada-tool-structure-component-key'
COMPONENT_DISPLAY_NAME_TYPE = 'ada-tool-structure-component-display-name'
COMPONENT_SCOPE_TYPE = 'ada-tool-structure-component-scope'
COMPONENT_SCOPE_WRAPPER_TYPE = 'ada-tool-structure-component-scope-wrapper'
COMPONENT_DELETE_TYPE = 'ada-tool-structure-component-delete'
COMPONENT_ADD_SUBCOMPONENT_TYPE = 'ada-tool-structure-component-add-subcomponent'
COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE = (
    'ada-tool-structure-component-subcomponents-container'
)
COMPONENT_SUMMARY_NAME_TYPE = 'ada-tool-structure-component-summary-name'
COMPONENT_SUMMARY_SCOPE_TYPE = 'ada-tool-structure-component-summary-scope'
COMPONENT_SUMMARY_COUNT_TYPE = 'ada-tool-structure-component-summary-count'

SUBCOMPONENT_ROW_TYPE = 'ada-tool-structure-subcomponent-row'
SUBCOMPONENT_KEY_TYPE = 'ada-tool-structure-subcomponent-key'
SUBCOMPONENT_DISPLAY_NAME_TYPE = 'ada-tool-structure-subcomponent-display-name'
SUBCOMPONENT_LINKED_TYPE = 'ada-tool-structure-subcomponent-linked'
SUBCOMPONENT_LINKED_WRAPPER_TYPE = 'ada-tool-structure-subcomponent-linked-wrapper'
SUBCOMPONENT_DELETE_TYPE = 'ada-tool-structure-subcomponent-delete'
SUBCOMPONENT_SUMMARY_NAME_TYPE = 'ada-tool-structure-subcomponent-summary-name'
SUBCOMPONENT_SUMMARY_LINK_TYPE = 'ada-tool-structure-subcomponent-summary-link'


def row_id(row_type: str, index: int) -> dict[str, object]:
    return {'type': row_type, 'index': index}


def component_nested_id(
    row_type: str,
    owner_index: int,
) -> dict[str, object]:
    return {'type': row_type, 'owner_index': owner_index}


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
