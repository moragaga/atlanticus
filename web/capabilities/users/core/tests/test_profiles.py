from atlanticus.web.profiles.models import (
    BASIC_PROFILE_KEY,
    GUEST_PROFILE_KEY,
    LOCAL_PROFILE,
    LOCAL_PROFILE_KEY,
    ROOT_PROFILE_KEY,
    ProfileCatalog,
)
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_JOHN
from atlanticus.web.users.profiles import available_managed_profiles


def test_assignable_profiles_include_root_and_exclude_guest_and_local():
    keys = {profile.key for profile in available_managed_profiles(ProfileCatalog())}
    assert BASIC_PROFILE_KEY in keys
    assert ROOT_PROFILE_KEY in keys
    assert GUEST_PROFILE_KEY not in keys
    assert LOCAL_PROFILE_KEY not in keys


def test_local_users_use_local_profile_presentation():
    for local in (LOCAL_JANE, LOCAL_JOHN):
        runtime = local.to_runtime_user()
        assert runtime.profile.id == LOCAL_PROFILE.key
        assert runtime.profile.background_color == LOCAL_PROFILE.background_color
        assert runtime.profile.text_color == LOCAL_PROFILE.text_color
        assert local.avatar_background_color.startswith('#')
        assert local.avatar_text_color == '#FFFFFF'
    assert LOCAL_JANE.avatar_background_color != LOCAL_JOHN.avatar_background_color
