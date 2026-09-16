CATALOG_STORE_ID = 'atlanticus-navigation-admin-catalog'
MOUNT_STORE_ID = 'atlanticus-navigation-admin-mounted'
LINK_EDITOR_STORE_ID = 'atlanticus-navigation-admin-link-editor'
GROUP_EDITOR_STORE_ID = 'atlanticus-navigation-admin-group-editor'
STRUCTURE_ID = 'atlanticus-navigation-admin-structure'
ADD_ROOT_LINK_ID = 'atlanticus-navigation-admin-add-root-link'
ADD_GROUP_ID = 'atlanticus-navigation-admin-add-group'
SAVE_BUTTON_ID = 'atlanticus-navigation-admin-save'
SAVE_RESULT_ID = 'atlanticus-navigation-admin-save-result'
IMPORT_UPLOAD_ID = 'atlanticus-navigation-admin-import'
IMPORT_RESULT_ID = 'atlanticus-navigation-admin-import-result'
SOURCE_NAME_ID = 'atlanticus-navigation-admin-source-name'
PROJECTION_NAME_ID = 'atlanticus-navigation-admin-projection-name'
LINK_MODAL_ID = 'atlanticus-navigation-admin-link-modal'
LINK_MODAL_TITLE_ID = 'atlanticus-navigation-admin-link-modal-title'
LINK_NAME_ID = 'atlanticus-navigation-admin-link-name'
LINK_KEY_ID = 'atlanticus-navigation-admin-link-key'
LINK_HREF_ID = 'atlanticus-navigation-admin-link-href'
LINK_ICON_ID = 'atlanticus-navigation-admin-link-icon'
LINK_SECTION_ID = 'atlanticus-navigation-admin-link-section'
LINK_ENABLED_ID = 'atlanticus-navigation-admin-link-enabled'
LINK_NEW_TAB_ID = 'atlanticus-navigation-admin-link-new-tab'
LINK_FORCE_RELOAD_ID = 'atlanticus-navigation-admin-link-force-reload'
LINK_PROFILES_ID = 'atlanticus-navigation-admin-link-profiles'
LINK_CANCEL_ID = 'atlanticus-navigation-admin-link-cancel'
LINK_SAVE_ID = 'atlanticus-navigation-admin-link-save'
LINK_RESULT_ID = 'atlanticus-navigation-admin-link-result'
GROUP_MODAL_ID = 'atlanticus-navigation-admin-group-modal'
GROUP_MODAL_TITLE_ID = 'atlanticus-navigation-admin-group-modal-title'
GROUP_NAME_ID = 'atlanticus-navigation-admin-group-name'
GROUP_KEY_ID = 'atlanticus-navigation-admin-group-key'
GROUP_ICON_ID = 'atlanticus-navigation-admin-group-icon'
GROUP_ENABLED_ID = 'atlanticus-navigation-admin-group-enabled'
GROUP_CANCEL_ID = 'atlanticus-navigation-admin-group-cancel'
GROUP_SAVE_ID = 'atlanticus-navigation-admin-group-save'
GROUP_RESULT_ID = 'atlanticus-navigation-admin-group-result'


def link_edit_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-link-edit', 'key': key}


def link_delete_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-link-delete', 'key': key}


def link_up_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-link-up', 'key': key}


def link_down_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-link-down', 'key': key}


def group_edit_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-group-edit', 'key': key}


def group_delete_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-group-delete', 'key': key}


def group_up_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-group-up', 'key': key}


def group_down_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-group-down', 'key': key}


def group_add_link_id(key: str) -> dict[str, str]:
    return {'type': 'atlanticus-navigation-group-add-link', 'key': key}
