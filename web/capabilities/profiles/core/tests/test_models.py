from pathlib import Path

import pytest

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import (
    SYSTEM_PROFILE_DEFINITIONS,
    SYSTEM_PROFILE_KEYS,
    ProfileCatalog,
    ProfileDefinition,
)


def test_profile_catalog_contains_system_profiles_by_default() -> None:
    catalog = ProfileCatalog()

    assert catalog.all() == SYSTEM_PROFILE_DEFINITIONS
    assert tuple(profile.key for profile in catalog.all()) == ('basic', 'root', 'guest', 'local')
    assert catalog.require('basic').background_color == '#EC407A'
    assert catalog.require('root').background_color == '#673AB7'
    assert catalog.require('guest').background_color == '#FF5722'
    assert catalog.require('local').background_color == '#3778C2'


def test_profile_catalog_appends_configured_profiles_and_preserves_order() -> None:
    administrator = ProfileDefinition(
        key='administrator',
        label='Administrador',
        background_color='#112233',
    )
    operator = ProfileDefinition(
        key='operator',
        label='Operador',
        background_color='#445566',
        text_color='#AABBCC',
    )

    catalog = ProfileCatalog(profiles=(administrator, operator))

    assert tuple(profile.key for profile in catalog.all()) == (
        'basic',
        'root',
        'guest',
        'local',
        'administrator',
        'operator',
    )
    assert catalog.require(' ADMINISTRATOR ') is administrator
    assert catalog.require(' operator ') is operator


@pytest.mark.parametrize('key', tuple(sorted(SYSTEM_PROFILE_KEYS)))
def test_profile_catalog_rejects_system_profile_redefinition(key: str) -> None:
    with pytest.raises(ProfilesDefinitionError, match='System profile'):
        ProfileCatalog(
            profiles=(
                ProfileDefinition(
                    key=key,
                    label='Replacement',
                    background_color='#112233',
                ),
            )
        )


def test_profile_catalog_allows_administrator_as_configured_profile() -> None:
    administrator = ProfileDefinition(
        key='administrator',
        label='Administrador',
        background_color='#112233',
    )

    catalog = ProfileCatalog(profiles=(administrator,))

    assert catalog.require('administrator') is administrator


def test_profile_catalog_rejects_duplicate_normalized_keys() -> None:
    first = ProfileDefinition(
        key='Operator',
        label='Operador',
        background_color='#112233',
    )
    duplicate = ProfileDefinition(
        key=' operator ',
        label='Operador alternativo',
        background_color='#445566',
    )

    with pytest.raises(ProfilesDefinitionError, match="Duplicate profile key 'operator'"):
        ProfileCatalog(profiles=(first, duplicate))


def test_profile_catalog_rejects_unknown_profile() -> None:
    catalog = ProfileCatalog()

    with pytest.raises(ProfilesDefinitionError, match="Unknown profile 'missing'"):
        catalog.require(' Missing ')


def test_profile_definition_normalizes_values() -> None:
    profile = ProfileDefinition(
        key=' Operator ',
        label=' Operador ',
        background_color=' #aabbcc ',
        text_color=' #112233 ',
    )

    assert profile == ProfileDefinition(
        key='operator',
        label='Operador',
        background_color='#AABBCC',
        text_color='#112233',
    )


def test_profiles_core_has_no_users_dependency() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-users' not in pyproject
    assert 'atlanticus.web.users' not in sources
