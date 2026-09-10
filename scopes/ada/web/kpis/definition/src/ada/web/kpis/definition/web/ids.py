ROOT_ID = 'ada-kpi-definition'
CONFIGURATION_STORE_ID = 'ada-kpi-definition--configuration'
QUERY_STORE_ID = 'ada-kpi-definition--query'
EDITOR_STORE_ID = 'ada-kpi-definition--editor'
SEARCH_ID = 'ada-kpi-definition--search'
STATUS_FILTER_ID = 'ada-kpi-definition--status-filter'
DEPENDENCY_ID = 'ada-kpi-definition--dependency'
GRID_CONTAINER_ID = 'ada-kpi-definition--grid'
PAGINATION_CONTAINER_ID = 'ada-kpi-definition--pagination'
TABLE_BODY_ID = 'ada-kpi-definition--table-body'
EDITOR_MODAL_ID = 'ada-kpi-definition--editor-modal'
EDITOR_BACKDROP_ID = 'ada-kpi-definition--editor-backdrop'
EDITOR_CLOSE_ID = 'ada-kpi-definition--editor-close'
EDITOR_TITLE_ID = 'ada-kpi-definition--editor-title'
EDITOR_RESULT_ID = 'ada-kpi-definition--editor-result'
EDITOR_KPI_KEY_ID = 'ada-kpi-definition--editor-kpi-key'
EDITOR_FORM_ID = 'ada-kpi-definition--editor-form'
EDITOR_DETAIL_ID = 'ada-kpi-definition--editor-detail'
EDITOR_VIEW_ID = 'ada-kpi-definition--editor-view'
EDITOR_SAVE_ID = 'ada-kpi-definition--editor-save'
EDITOR_CANCEL_ID = 'ada-kpi-definition--editor-cancel'
PAGINATION_PREFIX = 'ada-kpi-definition'
ROW_ADD_TYPE = 'ada-kpi-definition--row-add'
ROW_VIEW_TYPE = 'ada-kpi-definition--row-view'
ROW_EDIT_TYPE = 'ada-kpi-definition--row-edit'
ROW_DELETE_TYPE = 'ada-kpi-definition--row-delete'


def row_add_id(kpi_key: object) -> dict[str, object]:
    return {'type': ROW_ADD_TYPE, 'key': kpi_key}


def row_view_id(kpi_key: object) -> dict[str, object]:
    return {'type': ROW_VIEW_TYPE, 'key': kpi_key}


def row_edit_id(kpi_key: object) -> dict[str, object]:
    return {'type': ROW_EDIT_TYPE, 'key': kpi_key}


def row_delete_id(kpi_key: object) -> dict[str, object]:
    return {'type': ROW_DELETE_TYPE, 'key': kpi_key}
