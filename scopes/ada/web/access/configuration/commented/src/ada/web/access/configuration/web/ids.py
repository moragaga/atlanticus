# IDs estables de la superficie Access.
# El modal usa inputs HTML con IDs dinámicos por access_key para evitar estado visual paralelo.

CONFIGURATION_STORE_ID = 'ada-access-admin-configuration'
MOUNT_STORE_ID = 'ada-access-admin-mounted'
VIEW_STORE_ID = 'ada-access-admin-view'
PROFILE_EDITOR_STORE_ID = 'ada-access-admin-profile-editor'
ACCESS_PAGE_STORE_ID = 'ada-access-admin-access-page'
PROFILE_PAGE_STORE_ID = 'ada-access-admin-profile-page'
SOURCE_NAME_ID = 'ada-access-admin-source-name'
PROJECTION_NAME_ID = 'ada-access-admin-projection-name'
ACCESS_TAB_ID = 'ada-access-admin-tab-accesses'
PROFILES_TAB_ID = 'ada-access-admin-tab-profiles'
ACCESS_PANEL_ID = 'ada-access-admin-panel-accesses'
PROFILES_PANEL_ID = 'ada-access-admin-panel-profiles'
ACCESS_SCOPE_INPUT_ID = 'ada-access-admin-access-scope'
ACCESS_PERMISSION_INPUT_ID = 'ada-access-admin-access-permission'
ACCESS_KEY_PREVIEW_ID = 'ada-access-admin-access-preview'
ADD_ACCESS_ID = 'ada-access-admin-add-access'
ADD_ACCESS_RESULT_ID = 'ada-access-admin-add-result'
ACCESS_LIST_ID = 'ada-access-admin-access-list'
ACCESS_PREVIOUS_ID = 'ada-access-admin-access-previous'
ACCESS_NEXT_ID = 'ada-access-admin-access-next'
ACCESS_PAGE_SIZE_ID = 'ada-access-admin-access-page-size'
PROFILE_ASSIGNMENTS_ID = 'ada-access-admin-profile-assignments'
PROFILE_PREVIOUS_ID = 'ada-access-admin-profile-previous'
PROFILE_NEXT_ID = 'ada-access-admin-profile-next'
PROFILE_PAGE_SIZE_ID = 'ada-access-admin-profile-page-size'
PROFILE_MODAL_ID = 'ada-access-admin-profile-modal'
PROFILE_MODAL_TITLE_ID = 'ada-access-admin-profile-modal-title'
PROFILE_MODAL_ACCESS_LIST_ID = 'ada-access-admin-profile-modal-access-list'
PROFILE_MODAL_RESULT_ID = 'ada-access-admin-profile-modal-result'
PROFILE_MODAL_SAVE_ID = 'ada-access-admin-profile-modal-save'
PROFILE_MODAL_CANCEL_ID = 'ada-access-admin-profile-modal-cancel'
PROFILE_MODAL_CLOSE_ID = 'ada-access-admin-profile-modal-close'
PROFILE_MODAL_BACKDROP_ID = 'ada-access-admin-profile-modal-backdrop'
SAVE_BUTTON_ID = 'ada-access-admin-save'
SAVE_RESULT_ID = 'ada-access-admin-save-result'


def access_remove_id(access_key: str) -> dict[str, str]:
    return {'type': 'ada-access-admin-remove', 'key': access_key}


def access_page_id(page_number: int) -> dict[str, int | str]:
    return {'type': 'ada-access-admin-access-page-number', 'index': page_number}


def profile_configure_id(profile_key: str) -> dict[str, str]:
    return {'type': 'ada-access-admin-profile-configure', 'profile_key': profile_key}


def profile_modal_access_id(access_key: str) -> dict[str, str]:
    return {'type': 'ada-access-admin-profile-modal-access', 'key': access_key}


def profile_page_id(page_number: int) -> dict[str, int | str]:
    return {'type': 'ada-access-admin-profile-page-number', 'index': page_number}
