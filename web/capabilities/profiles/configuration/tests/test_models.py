from __future__ import annotations

import pytest

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileDefinition


def _profile(key: str, color: str = '#123456') -> ProfileDefinition:
    return ProfileDefinition(
        key=key,
        label=key.title(),
        background_color=color,
        text_color='#FFFFFF',
    )


def test_profiles_configuration_round_trips_configured_profiles() -> None:
    configuration = ProfilesConfiguration(
        profiles=(_profile('administrator'), _profile('operator'))
    )

    restored = ProfilesConfiguration.from_document(configuration.to_document())

    assert restored == configuration
    assert [profile.key for profile in restored.catalog().all()] == [
        'administrator',
        'operator',
    ]


def test_profiles_configuration_rejects_duplicate_normalized_keys() -> None:
    with pytest.raises(ProfilesDefinitionError, match='Duplicate profile key'):
        ProfilesConfiguration(
            profiles=(
                _profile('Operator'),
                _profile('operator'),
            )
        )
