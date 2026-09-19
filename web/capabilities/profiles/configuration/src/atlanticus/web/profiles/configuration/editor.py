from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from atlanticus.web.profiles.configuration.models import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileDefinition, normalize_profile_key


def build_initial_configuration() -> ProfilesConfiguration:
    return ProfilesConfiguration()


def create_profile(
    configuration: ProfilesConfiguration,
    *,
    label: str,
    background_color: str,
    text_color: str = '#FFFFFF',
) -> ProfilesConfiguration:
    profile = ProfileDefinition(
        key=str(uuid4()),
        label=label,
        background_color=background_color,
        text_color=text_color,
    )
    return replace(configuration, profiles=(*configuration.profiles, profile))


def update_profile(
    configuration: ProfilesConfiguration,
    *,
    key: str,
    label: str,
    background_color: str,
    text_color: str,
) -> ProfilesConfiguration:
    normalized_key = normalize_profile_key(key)
    found = False
    profiles: list[ProfileDefinition] = []
    for profile in configuration.profiles:
        if profile.key != normalized_key:
            profiles.append(profile)
            continue
        found = True
        profiles.append(
            ProfileDefinition(
                key=profile.key,
                label=label,
                background_color=background_color,
                text_color=text_color,
            )
        )
    if not found:
        raise ProfilesDefinitionError(f'Configured profile {normalized_key!r} does not exist')
    return replace(configuration, profiles=tuple(profiles))
