import pytest

from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_JOHN, select_local_user
from atlanticus.web.users.profiles import (
    available_managed_profiles,
    has_full_access_profile,
    require_managed_profile,
)


def _profiles() -> ProfileCatalog:
    return ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='11111111-1111-4111-8111-111111111111',
                label='Analista',
                background_color='#112233',
            ),
        )
    )


def test_managed_profiles_include_system_and_configured_profiles_except_local() -> None:
    profiles = _profiles()

    assert tuple(profile.key for profile in available_managed_profiles(profiles)) == (
        'basic',
        'root',
        'guest',
        '11111111-1111-4111-8111-111111111111',
    )
    assert require_managed_profile('guest', profiles=profiles).key == 'guest'
    assert require_managed_profile(
        '11111111-1111-4111-8111-111111111111',
        profiles=profiles,
    ).label == 'Analista'


def test_managed_profile_rejects_local_and_unknown_profile() -> None:
    profiles = _profiles()

    with pytest.raises(UsersDefinitionError, match='must not be local'):
        require_managed_profile('local', profiles=profiles)
    with pytest.raises(UsersDefinitionError, match='Unknown managed user profile'):
        require_managed_profile('missing', profiles=profiles)


def test_root_and_local_are_full_access_profiles() -> None:
    assert has_full_access_profile('root') is True
    assert has_full_access_profile('local') is True
    assert has_full_access_profile('basic') is False
    assert has_full_access_profile('guest') is False


def test_local_selector_preserves_jane_and_john_profiles_and_visuals() -> None:
    jane = select_local_user(selector=lambda users: users[0])
    john = select_local_user(selector=lambda users: users[1])

    assert jane.display_name == 'Jane Doe'
    assert jane.subject_id == LOCAL_JANE.subject_id
    assert jane.profile_key == 'local'
    assert jane.avatar_background_color == '#C85D91'
    assert jane.avatar_text_color == '#FFFFFF'
    assert jane.is_local is True
    assert jane.has_full_access is True

    assert john.display_name == 'John Doe'
    assert john.subject_id == LOCAL_JOHN.subject_id
    assert john.profile_key == 'local'
    assert john.avatar_background_color == '#3778C2'
    assert john.avatar_text_color == '#FFFFFF'
    assert john.is_local is True
    assert john.has_full_access is True
