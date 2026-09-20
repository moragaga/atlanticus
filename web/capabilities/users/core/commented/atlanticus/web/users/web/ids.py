# Espejo pedagógico: Users separa vistas, paginación y editor modal sin cambiar el contrato administrativo.
SNAPSHOT_ID = 'atlanticus-users-admin-snapshot'
REFRESH_ID = 'atlanticus-users-admin-refresh'
REFRESH_RESULT_ID = 'atlanticus-users-admin-refresh-result'

VIEW_ID = 'atlanticus-users-admin-view'
MANAGED_TAB_ID = 'atlanticus-users-admin-managed-tab'
PROMOTION_TAB_ID = 'atlanticus-users-admin-promotion-tab'
MANAGED_PANEL_ID = 'atlanticus-users-admin-managed-panel'
PROMOTION_PANEL_ID = 'atlanticus-users-admin-promotion-panel'

PROMOTION_SEARCH_ID = 'atlanticus-users-admin-promotion-search'
PROMOTION_STATE_ID = 'atlanticus-users-admin-promotion-state'
PROMOTION_LIST_ID = 'atlanticus-users-admin-promotion-list'
PROMOTION_PAGE_SIZE_ID = 'atlanticus-users-admin-promotion-page-size'
PROMOTION_PAGE_ID = 'atlanticus-users-admin-promotion-page'
PROMOTION_ROWS_ID = 'atlanticus-users-admin-promotion-rows'
PROMOTION_STATUS_ID = 'atlanticus-users-admin-promotion-status'
PROMOTION_PREVIOUS_ID = 'atlanticus-users-admin-promotion-previous'
PROMOTION_NEXT_ID = 'atlanticus-users-admin-promotion-next'
PROMOTION_RESULT_ID = 'atlanticus-users-admin-promotion-result'

MANAGED_SEARCH_ID = 'atlanticus-users-admin-managed-search'
MANAGED_PROFILE_ID = 'atlanticus-users-admin-managed-profile'
MANAGED_ENABLED_ID = 'atlanticus-users-admin-managed-enabled'
MANAGED_LIST_ID = 'atlanticus-users-admin-managed-list'
MANAGED_PAGE_SIZE_ID = 'atlanticus-users-admin-managed-page-size'
MANAGED_PAGE_ID = 'atlanticus-users-admin-managed-page'
MANAGED_ROWS_ID = 'atlanticus-users-admin-managed-rows'
MANAGED_STATUS_ID = 'atlanticus-users-admin-managed-status'
MANAGED_PREVIOUS_ID = 'atlanticus-users-admin-managed-previous'
MANAGED_NEXT_ID = 'atlanticus-users-admin-managed-next'

EDIT_MODAL_ID = 'atlanticus-users-admin-edit-modal'
EDIT_SELECTED_ID = 'atlanticus-users-admin-edit-selected'
EDIT_TITLE_ID = 'atlanticus-users-admin-edit-title'
EDIT_IDENTITY_ID = 'atlanticus-users-admin-edit-identity'
EDIT_PROFILE_ID = 'atlanticus-users-admin-edit-profile'
EDIT_ENABLED_ID = 'atlanticus-users-admin-edit-enabled'
EDIT_SAVE_ID = 'atlanticus-users-admin-edit-save'
EDIT_CANCEL_ID = 'atlanticus-users-admin-edit-cancel'
EDIT_CLOSE_ID = 'atlanticus-users-admin-edit-close'
EDIT_BACKDROP_ID = 'atlanticus-users-admin-edit-backdrop'
EDIT_RESULT_ID = 'atlanticus-users-admin-edit-result'


def candidate_profile_id(user_id: str) -> dict[str, str]:
    return {'type': 'atlanticus-users-admin-candidate-profile', 'user_id': user_id}


def candidate_promote_id(user_id: str) -> dict[str, str]:
    return {'type': 'atlanticus-users-admin-candidate-promote', 'user_id': user_id}


def managed_edit_id(user_id: str) -> dict[str, str]:
    return {'type': 'atlanticus-users-admin-managed-edit', 'user_id': user_id}


def promotion_page_number_id(page_number: int | str) -> dict[str, int | str]:
    return {'type': 'atlanticus-users-admin-promotion-page-number', 'index': page_number}


def managed_page_number_id(page_number: int | str) -> dict[str, int | str]:
    return {'type': 'atlanticus-users-admin-managed-page-number', 'index': page_number}
