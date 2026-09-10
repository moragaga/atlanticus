ROOT_ID = 'ada-kpi-configuration'
CONFIGURATION_STORE_ID = 'ada-kpi-configuration--configuration'
QUERY_STORE_ID = 'ada-kpi-configuration--query'
EDITOR_STORE_ID = 'ada-kpi-configuration--editor'
SEARCH_ID = 'ada-kpi-configuration--search'
DESTINATION_FILTER_ID = 'ada-kpi-configuration--destination-filter'
DATA_MODE_FILTER_ID = 'ada-kpi-configuration--data-mode-filter'
ADD_BUTTON_ID = 'ada-kpi-configuration--add'
ACTIVE_FILTERS_ID = 'ada-kpi-configuration--active-filters'
AVAILABILITY_ID = 'ada-kpi-configuration--availability'
GRID_CONTAINER_ID = 'ada-kpi-configuration--grid'
PAGINATION_CONTAINER_ID = 'ada-kpi-configuration--pagination'
TABLE_BODY_ID = 'ada-kpi-configuration--table-body'
EDITOR_MODAL_ID = 'ada-kpi-configuration--editor-modal'
EDITOR_BACKDROP_ID = 'ada-kpi-configuration--editor-backdrop'
EDITOR_CLOSE_ID = 'ada-kpi-configuration--editor-close'
EDITOR_TITLE_ID = 'ada-kpi-configuration--editor-title'
EDITOR_RESULT_ID = 'ada-kpi-configuration--editor-result'
EDITOR_KPI_KEY_ID = 'ada-kpi-configuration--editor-kpi-key'
EDITOR_LATEST_ID = 'ada-kpi-configuration--editor-latest'
EDITOR_SERIES_ID = 'ada-kpi-configuration--editor-series'
EDITOR_HOURS_ID = 'ada-kpi-configuration--editor-hours'
EDITOR_DESTINATIONS_ID = 'ada-kpi-configuration--editor-destinations'
EDITOR_SAVE_ID = 'ada-kpi-configuration--editor-save'
EDITOR_CANCEL_ID = 'ada-kpi-configuration--editor-cancel'
PAGINATION_PREFIX = 'ada-kpi-configuration'
ROW_EDIT_TYPE = 'ada-kpi-configuration--row-edit'
ROW_DELETE_TYPE = 'ada-kpi-configuration--row-delete'


def row_edit_id(kpi_key: object) -> dict[str, object]:
    return {'type': ROW_EDIT_TYPE, 'key': kpi_key}


def row_delete_id(kpi_key: object) -> dict[str, object]:
    return {'type': ROW_DELETE_TYPE, 'key': kpi_key}
