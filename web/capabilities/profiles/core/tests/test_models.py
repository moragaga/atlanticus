from pathlib import Path

import pytest

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


def test_profile_catalog_is_empty_by_default() -> None:
    catalog = ProfileCatalog()

    assert catalog.all() == ()


def test_profile_catalog_preserves_explicit_profiles_and_order() -> None:
    administrator = ProfileDefinition(
        key='administrator',
        label='Administrador',
        background_color='#673AB7',
    )
    operator = ProfileDefinition(
        key='operator',
        label='Operador',
        background_color='#112233',
        text_color='#AABBCC',
    )

    catalog = ProfileCatalog(profiles=(administrator, operator))

    assert catalog.all() == (administrator, operator)
    assert catalog.require('ADMINISTRATOR') is administrator
    assert catalog.require(' operator ') is operator


def test_profile_catalog_accepts_identity_and_users_terms_as_ordinary_keys() -> None:
    profiles = tuple(
        ProfileDefinition(
            key=key,
            label=key.title(),
            background_color='#112233',
        )
        for key in ('local', 'guest', 'root')
    )

    catalog = ProfileCatalog(profiles=profiles)

    assert tuple(profile.key for profile in catalog.all()) == ('local', 'guest', 'root')


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
