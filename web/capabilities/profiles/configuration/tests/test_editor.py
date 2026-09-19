from uuid import UUID

import pytest

from atlanticus.web.profiles.configuration import (
    ProfilesConfiguration,
    build_initial_configuration,
    create_profile,
    update_profile,
)
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileDefinition


def _profile(
    key: str,
    *,
    label: str | None = None,
    background_color: str = '#123456',
    text_color: str = '#FFFFFF',
) -> ProfileDefinition:
    return ProfileDefinition(
        key=key,
        label=label or key.title(),
        background_color=background_color,
        text_color=text_color,
    )


def test_initial_configuration_contains_no_configured_profiles() -> None:
    configuration = build_initial_configuration()

    assert configuration.profiles == ()
    assert [profile.key for profile in configuration.catalog().all()] == [
        'basic',
        'root',
        'guest',
        'local',
    ]


def test_create_profile_generates_uuid4_independent_from_label() -> None:
    configuration = create_profile(
        ProfilesConfiguration(),
        label='Jefe Supremación',
        background_color='#123456',
        text_color='#ABCDEF',
    )

    profile = configuration.profiles[0]
    parsed_key = UUID(profile.key)

    assert parsed_key.version == 4
    assert profile.label == 'Jefe Supremación'
    assert profile.key != 'jefe-supremacion'
    assert profile.background_color == '#123456'
    assert profile.text_color == '#ABCDEF'


def test_create_profile_preserves_existing_configured_profiles_and_order() -> None:
    administrator = _profile('administrator', label='Administrador')
    original = ProfilesConfiguration(profiles=(administrator,))

    updated = create_profile(
        original,
        label='Operación Planta',
        background_color='#654321',
    )

    assert original.profiles == (administrator,)
    assert updated.profiles[0] is administrator
    assert updated.profiles[1].label == 'Operación Planta'
    assert UUID(updated.profiles[1].key).version == 4


def test_update_profile_changes_visible_values_without_changing_key_or_order() -> None:
    first = _profile('administrator', label='Administrador')
    second = create_profile(
        ProfilesConfiguration(profiles=(first,)),
        label='Operador',
        background_color='#123456',
    ).profiles[1]
    configuration = ProfilesConfiguration(profiles=(first, second))

    updated = update_profile(
        configuration,
        key=second.key,
        label='Jefe Supremación',
        background_color='#ABCDEF',
        text_color='#112233',
    )

    assert [profile.key for profile in updated.profiles] == [first.key, second.key]
    assert updated.profiles[0] is first
    assert updated.profiles[1].key == second.key
    assert updated.profiles[1].label == 'Jefe Supremación'
    assert updated.profiles[1].background_color == '#ABCDEF'
    assert updated.profiles[1].text_color == '#112233'


def test_update_profile_preserves_legacy_textual_configured_key() -> None:
    configuration = ProfilesConfiguration(
        profiles=(_profile('administrator', label='Administrador'),)
    )

    updated = update_profile(
        configuration,
        key=' ADMINISTRATOR ',
        label='Administrador General',
        background_color='#654321',
        text_color='#FFFFFF',
    )

    assert updated.profiles[0].key == 'administrator'
    assert updated.profiles[0].label == 'Administrador General'


@pytest.mark.parametrize('key', ('basic', 'root', 'guest', 'local'))
def test_update_profile_cannot_edit_system_profiles(key: str) -> None:
    with pytest.raises(ProfilesDefinitionError, match='Configured profile'):
        update_profile(
            ProfilesConfiguration(),
            key=key,
            label='Modified',
            background_color='#123456',
            text_color='#FFFFFF',
        )


def test_update_profile_rejects_unknown_configured_profile() -> None:
    with pytest.raises(ProfilesDefinitionError, match="'missing' does not exist"):
        update_profile(
            ProfilesConfiguration(),
            key='missing',
            label='Missing',
            background_color='#123456',
            text_color='#FFFFFF',
        )


def test_editor_delegates_profile_validation_to_domain_model() -> None:
    with pytest.raises(ProfilesDefinitionError, match='Profile label must not be empty'):
        create_profile(
            ProfilesConfiguration(),
            label=' ',
            background_color='#123456',
        )

    with pytest.raises(ProfilesDefinitionError, match='#RRGGBB'):
        update_profile(
            ProfilesConfiguration(profiles=(_profile('administrator'),)),
            key='administrator',
            label='Administrador',
            background_color='red',
            text_color='#FFFFFF',
        )
