from pathlib import Path

import pytest

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import (
    ADMINISTRATOR_PROFILE_KEY,
    DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
    DEFAULT_ADMINISTRATOR_TEXT_COLOR,
    DEFAULT_GUEST_BACKGROUND_COLOR,
    DEFAULT_GUEST_TEXT_COLOR,
    GUEST_PROFILE_KEY,
    LOCAL_PROFILE_BACKGROUND_COLOR,
    LOCAL_PROFILE_KEY,
    LOCAL_PROFILE_TEXT_COLOR,
    ProfileCatalog,
    ProfileDefinition,
)


def test_system_profiles_preserve_current_contract_during_extraction() -> None:
    default = ProfileCatalog()
    changed = ProfileCatalog(
        administrator_background_color='#112233',
        administrator_text_color='#AABBCC',
    )

    assert tuple(profile.key for profile in default.all()) == (
        'local',
        'administrator',
        'guest',
    )
    assert default.require(LOCAL_PROFILE_KEY).background_color == LOCAL_PROFILE_BACKGROUND_COLOR
    assert default.require(LOCAL_PROFILE_KEY).text_color == LOCAL_PROFILE_TEXT_COLOR
    assert (
        default.require(ADMINISTRATOR_PROFILE_KEY).background_color
        == DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR
    )
    assert default.require(ADMINISTRATOR_PROFILE_KEY).text_color == DEFAULT_ADMINISTRATOR_TEXT_COLOR
    assert default.require(GUEST_PROFILE_KEY).background_color == DEFAULT_GUEST_BACKGROUND_COLOR
    assert default.require(GUEST_PROFILE_KEY).text_color == DEFAULT_GUEST_TEXT_COLOR
    assert changed.require(ADMINISTRATOR_PROFILE_KEY).background_color == '#112233'


def test_system_profiles_cannot_be_redefined_as_custom_profiles() -> None:
    with pytest.raises(ProfilesDefinitionError, match='cannot be redefined'):
        ProfileCatalog(
            custom_profiles=(
                ProfileDefinition(
                    key='administrator',
                    label='Owner',
                    background_color='#000000',
                ),
            )
        )


def test_profiles_core_has_no_users_dependency() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-users' not in pyproject
    assert 'atlanticus.web.users' not in sources
