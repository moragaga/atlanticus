import pytest

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.profiles import (
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


def test_system_profiles_have_fixed_contracts_and_configurable_visuals() -> None:
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
    assert changed.require(ADMINISTRATOR_PROFILE_KEY).label == 'Administrador'
    assert changed.require(ADMINISTRATOR_PROFILE_KEY).background_color == '#112233'
    assert changed.require(ADMINISTRATOR_PROFILE_KEY).text_color == '#AABBCC'


def test_system_profiles_cannot_be_redefined_as_custom_profiles() -> None:
    with pytest.raises(UsersDefinitionError, match='cannot be redefined'):
        ProfileCatalog(
            custom_profiles=(
                ProfileDefinition(
                    key='administrator',
                    label='Owner',
                    background_color='#000000',
                    text_color='#FFFFFF',
                ),
            )
        )


def test_only_administrator_and_custom_profiles_are_assignable() -> None:
    catalog = ProfileCatalog(
        custom_profiles=(
            ProfileDefinition(
                key='operator',
                label='Operador',
                background_color='#123456',
                text_color='#FFFFFF',
            ),
        )
    )

    assert tuple(profile.key for profile in catalog.assignable()) == (
        'administrator',
        'operator',
    )


def test_guest_remains_a_system_profile_but_is_not_assignable() -> None:
    catalog = ProfileCatalog(
        guest_background_color='#123456',
        guest_text_color='#FEDCBA',
    )

    guest = catalog.require(GUEST_PROFILE_KEY)

    assert guest.background_color == '#123456'
    assert guest.text_color == '#FEDCBA'
    assert GUEST_PROFILE_KEY not in {profile.key for profile in catalog.assignable()}


def test_users_core_has_no_navigation_dependency() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-navigation' not in pyproject
    assert 'atlanticus.web.navigation' not in sources
