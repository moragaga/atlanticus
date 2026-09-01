import pytest

from atlanticus.web.users.configuration import (
    UserConfiguration,
    UserProfileConfiguration,
    UsersConfigurationCatalog,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError


def test_catalog_configures_system_colors_and_custom_profiles() -> None:
    catalog = UsersConfigurationCatalog(
        administrator_background_color='#112233',
        administrator_text_color='#FFFFFF',
        guest_background_color='#445566',
        guest_text_color='#000000',
        profiles=(
            UserProfileConfiguration(
                key='operator',
                label='Operador',
                background_color='#778899',
                text_color='#101010',
            ),
        ),
        users=(
            UserConfiguration.create(
                display_name='Ada User',
                email='ada@example.com',
                profile_key='operator',
            ),
        ),
    )

    profiles = catalog.profile_catalog()
    assert profiles.require('administrator').background_color == '#112233'
    assert profiles.require('administrator').text_color == '#FFFFFF'
    assert profiles.require('guest').background_color == '#445566'
    assert profiles.require('guest').text_color == '#000000'
    assert profiles.require('operator').background_color == '#778899'
    assert profiles.require('operator').text_color == '#101010'
    assert [item.key for item in profiles.restricted_access_profiles()] == ['guest', 'operator']


def test_system_profile_cannot_be_redefined() -> None:
    with pytest.raises(UsersConfigurationValidationError):
        UserProfileConfiguration(
            key='guest',
            label='Otro invitado',
            background_color='#123456',
        )


def test_user_can_be_preprovisioned_by_email() -> None:
    user = UserConfiguration.create(
        display_name='Preprovisioned User',
        email='User@Example.com',
        profile_key='administrator',
    )

    assert user.user_id.startswith('user:')
    assert user.email == 'user@example.com'
    assert user.issuer is None
    assert user.subject_id is None


def test_profile_key_is_generated_from_display_label() -> None:
    from atlanticus.web.users.configuration import build_profile_key

    assert build_profile_key('Operador Planta') == 'operador_planta'
    assert build_profile_key('Supervisión Mina') == 'supervision_mina'
