from __future__ import annotations

import pytest

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
    split_legacy_users_configuration_catalog,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.configuration.models import (
    UserConfiguration,
    UserProfileConfiguration,
    UsersConfigurationCatalog,
)


def _profile(key: str, color: str = '#123456') -> ProfileDefinition:
    return ProfileDefinition(
        key=key,
        label=key.title(),
        background_color=color,
        text_color='#FFFFFF',
    )


def _user(profile_key: str = 'operator', subject_id: str = 'subject-1') -> UserConfiguration:
    return UserConfiguration.create(
        display_name='Jane Doe',
        email=f'{subject_id}@example.com',
        profile_key=profile_key,
        issuer='issuer',
        subject_id=subject_id,
    )


def test_users_configuration_owns_only_managed_users() -> None:
    configuration = UsersConfiguration(users=(_user(),))

    assert configuration.to_document() == {'users': [configuration.users[0].to_document()]}
    assert UsersConfiguration.from_document(configuration.to_document()) == configuration


def test_composition_requires_administrator_profile() -> None:
    with pytest.raises(UsersConfigurationValidationError, match="Unknown profile 'administrator'"):
        UsersProfilesConfiguration(
            users=UsersConfiguration(),
            profiles=ProfilesConfiguration(profiles=(_profile('operator'),)),
        )


def test_composition_rejects_orphan_managed_user_even_when_disabled() -> None:
    disabled = UserConfiguration.create(
        display_name='Disabled User',
        email='disabled@example.com',
        profile_key='operator',
        enabled=False,
        issuer='issuer',
        subject_id='disabled',
    )
    with pytest.raises(UsersConfigurationValidationError, match="Unknown profile 'operator'"):
        UsersProfilesConfiguration(
            users=UsersConfiguration(users=(disabled,)),
            profiles=ProfilesConfiguration(profiles=(_profile('administrator'),)),
        )


@pytest.mark.parametrize('key', ['guest', 'local'])
def test_composition_rejects_non_functional_profile_keys(key: str) -> None:
    with pytest.raises(UsersConfigurationValidationError, match='functional profiles'):
        UsersProfilesConfiguration(
            users=UsersConfiguration(),
            profiles=ProfilesConfiguration(
                profiles=(_profile('administrator'), _profile(key))
            ),
        )


def test_legacy_catalog_split_materializes_administrator_and_drops_guest_authoring_fields() -> None:
    legacy = UsersConfigurationCatalog(
        administrator_background_color='#010203',
        administrator_text_color='#AABBCC',
        guest_background_color='#111111',
        guest_text_color='#222222',
        profiles=(
            UserProfileConfiguration(
                key='operator',
                label='Operator',
                background_color='#334455',
            ),
        ),
        users=(_user(),),
    )

    split = split_legacy_users_configuration_catalog(legacy)

    assert split.users.users == legacy.users
    assert [profile.key for profile in split.profiles.profiles] == ['administrator', 'operator']
    administrator = split.profiles.catalog().require('administrator')
    assert administrator.background_color == '#010203'
    assert administrator.text_color == '#AABBCC'
    assert all(profile.key != 'guest' for profile in split.profiles.profiles)
    assert 'guest_background_color' not in split.to_document()
