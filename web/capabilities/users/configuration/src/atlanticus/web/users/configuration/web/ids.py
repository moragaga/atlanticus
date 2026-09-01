CATALOG_STORE_ID = 'atlanticus-users-admin-catalog-store'
SOURCE_REVISION_STORE_ID = 'atlanticus-users-admin-source-revision-store'
SECTION_STORE_ID = 'atlanticus-users-admin-section-store'
PROFILE_EDITOR_STORE_ID = 'atlanticus-users-admin-profile-editor-store'
USER_EDITOR_STORE_ID = 'atlanticus-users-admin-user-editor-store'
MOUNT_STORE_ID = 'atlanticus-users-admin-mount-store'
IMPORT_UPLOAD_ID = 'atlanticus-users-admin-import-upload'
IMPORT_RESULT_ID = 'atlanticus-users-admin-import-result'
SOURCE_NAME_ID = 'atlanticus-users-admin-source-name'
PROJECTION_NAME_ID = 'atlanticus-users-admin-projection-name'
PROFILE_TAB_ID = 'atlanticus-users-admin-profile-tab'
USERS_TAB_ID = 'atlanticus-users-admin-users-tab'
DISCOVERED_TAB_ID = 'atlanticus-users-admin-discovered-tab'
PROFILE_PANEL_ID = 'atlanticus-users-admin-profile-panel'
USERS_PANEL_ID = 'atlanticus-users-admin-users-panel'
DISCOVERED_PANEL_ID = 'atlanticus-users-admin-discovered-panel'
ADMINISTRATOR_BACKGROUND_COLOR_ID = 'atlanticus-users-admin-administrator-background-color'
ADMINISTRATOR_TEXT_COLOR_ID = 'atlanticus-users-admin-administrator-text-color'
ADMINISTRATOR_PREVIEW_ID = 'atlanticus-users-admin-administrator-preview'
GUEST_BACKGROUND_COLOR_ID = 'atlanticus-users-admin-guest-background-color'
GUEST_TEXT_COLOR_ID = 'atlanticus-users-admin-guest-text-color'
GUEST_PREVIEW_ID = 'atlanticus-users-admin-guest-preview'
PROFILES_LIST_ID = 'atlanticus-users-admin-profiles-list'
ADD_PROFILE_ID = 'atlanticus-users-admin-add-profile'
PROFILE_MODAL_ID = 'atlanticus-users-admin-profile-modal'
PROFILE_MODAL_TITLE_ID = 'atlanticus-users-admin-profile-modal-title'
PROFILE_NAME_ID = 'atlanticus-users-admin-profile-name'
PROFILE_KEY_ID = 'atlanticus-users-admin-profile-key'
PROFILE_BACKGROUND_COLOR_ID = 'atlanticus-users-admin-profile-background-color'
PROFILE_TEXT_COLOR_ID = 'atlanticus-users-admin-profile-text-color'
PROFILE_PREVIEW_ID = 'atlanticus-users-admin-profile-preview'
PROFILE_SAVE_ID = 'atlanticus-users-admin-profile-save'
PROFILE_CANCEL_ID = 'atlanticus-users-admin-profile-cancel'
PROFILE_RESULT_ID = 'atlanticus-users-admin-profile-result'
USERS_LIST_ID = 'atlanticus-users-admin-users-list'
ADD_USER_ID = 'atlanticus-users-admin-add-user'
USER_MODAL_ID = 'atlanticus-users-admin-user-modal'
USER_MODAL_TITLE_ID = 'atlanticus-users-admin-user-modal-title'
USER_NAME_ID = 'atlanticus-users-admin-user-name'
USER_EMAIL_ID = 'atlanticus-users-admin-user-email'
USER_PROFILE_ID = 'atlanticus-users-admin-user-profile'
USER_ENABLED_ID = 'atlanticus-users-admin-user-enabled'
USER_SAVE_ID = 'atlanticus-users-admin-user-save'
USER_CANCEL_ID = 'atlanticus-users-admin-user-cancel'
USER_RESULT_ID = 'atlanticus-users-admin-user-result'
DISCOVERED_LIST_ID = 'atlanticus-users-admin-discovered-list'
DISCOVERED_REFRESH_ID = 'atlanticus-users-admin-discovered-refresh'
SAVE_BUTTON_ID = 'atlanticus-users-admin-save'
SAVE_RESULT_ID = 'atlanticus-users-admin-save-result'


def color_picker_button_id(picker_id: str) -> str:
    return f'{picker_id}-picker'


def color_picker_swatch_id(picker_id: str) -> str:
    return f'{picker_id}-swatch'


def profile_edit_id(key: str | object) -> dict[str, object]:
    return {'type': 'atlanticus-users-admin-profile-edit', 'key': key}


def profile_delete_id(key: str | object) -> dict[str, object]:
    return {'type': 'atlanticus-users-admin-profile-delete', 'key': key}


def user_edit_id(user_id: str | object) -> dict[str, object]:
    return {'type': 'atlanticus-users-admin-user-edit', 'user_id': user_id}


def discovered_add_id(user_id: str | object) -> dict[str, object]:
    return {'type': 'atlanticus-users-admin-discovered-add', 'user_id': user_id}
