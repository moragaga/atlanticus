CONFIGURATION_STORE_ID = 'ada-access-admin-configuration'
MOUNT_STORE_ID = 'ada-access-admin-mounted'
SOURCE_NAME_ID = 'ada-access-admin-source-name'
PROJECTION_NAME_ID = 'ada-access-admin-projection-name'
ACCESS_KEY_INPUT_ID = 'ada-access-admin-access-key'
ADD_ACCESS_ID = 'ada-access-admin-add-access'
ADD_ACCESS_RESULT_ID = 'ada-access-admin-add-result'
ACCESS_LIST_ID = 'ada-access-admin-access-list'
PROFILE_ASSIGNMENTS_ID = 'ada-access-admin-profile-assignments'
APPLY_ASSIGNMENTS_ID = 'ada-access-admin-apply-assignments'
ASSIGNMENTS_RESULT_ID = 'ada-access-admin-assignments-result'
SAVE_BUTTON_ID = 'ada-access-admin-save'
SAVE_RESULT_ID = 'ada-access-admin-save-result'


def access_remove_id(access_key: str) -> dict[str, str]:
    return {'type': 'ada-access-admin-remove', 'key': access_key}


def profile_access_id(profile_key: str) -> dict[str, str]:
    return {'type': 'ada-access-admin-profile-access', 'profile_key': profile_key}
