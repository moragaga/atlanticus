from __future__ import annotations

import pytest

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.configuration.models import UserConfiguration


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
