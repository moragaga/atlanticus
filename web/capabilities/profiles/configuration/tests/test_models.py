from __future__ import annotations

import pytest

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import SYSTEM_PROFILE_KEYS, ProfileDefinition


def _profile(key: str, color: str = '#123456') -> ProfileDefinition:
    return ProfileDefinition(
        key=key,
        label=key.title(),
        background_color=color,
        text_color='#FFFFFF',
    )


def test_profiles_configuration_round_trips_only_configured_profiles() -> None:
    configuration = ProfilesConfiguration(
        profiles=(_profile('administrator'), _profile('operator'))
    )

    document = configuration.to_document()
    restored = ProfilesConfiguration.from_document(document)

    assert restored == configuration
    assert [item['key'] for item in document['profiles']] == ['administrator', 'operator']
    assert [profile.key for profile in restored.profiles] == ['administrator', 'operator']
    assert [profile.key for profile in restored.catalog().all()] == [
        'basic',
        'root',
        'guest',
        'local',
        'administrator',
        'operator',
    ]


def test_profiles_configuration_allows_administrator_profile() -> None:
    configuration = ProfilesConfiguration(profiles=(_profile('administrator'),))

    assert configuration.catalog().require('administrator').key == 'administrator'


@pytest.mark.parametrize('key', tuple(sorted(SYSTEM_PROFILE_KEYS)))
def test_profiles_configuration_rejects_system_profile_redefinition(key: str) -> None:
    with pytest.raises(ProfilesDefinitionError, match='System profile'):
        ProfilesConfiguration(profiles=(_profile(key),))


def test_profiles_configuration_rejects_duplicate_normalized_keys() -> None:
    with pytest.raises(ProfilesDefinitionError, match='Duplicate profile key'):
        ProfilesConfiguration(
            profiles=(
                _profile('Operator'),
                _profile('operator'),
            )
        )
