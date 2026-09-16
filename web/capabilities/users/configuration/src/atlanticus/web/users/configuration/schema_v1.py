from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileDefinition, normalize_profile_color
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.configuration.models import UserConfiguration


def decode_users_profiles_schema_v1(
    document: Mapping[str, Any],
) -> UsersProfilesConfiguration:
    try:
        raw_profiles = document.get('profiles', [])
        raw_users = document.get('users', [])
        if not isinstance(raw_profiles, list) or not all(
            isinstance(item, dict) for item in raw_profiles
        ):
            raise TypeError
        if not isinstance(raw_users, list) or not all(
            isinstance(item, dict) for item in raw_users
        ):
            raise TypeError
        normalize_profile_color(str(document['guest_background_color']))
        normalize_profile_color(str(document['guest_text_color']))
        administrator = ProfileDefinition(
            key='administrator',
            label='Administrador',
            background_color=str(document['administrator_background_color']),
            text_color=str(document['administrator_text_color']),
        )
        profiles = tuple(
            ProfileDefinition(
                key=str(item['key']),
                label=str(item['label']),
                background_color=str(item['background_color']),
                text_color=str(item['text_color']),
            )
            for item in raw_profiles
        )
        return UsersProfilesConfiguration(
            users=UsersConfiguration(
                users=tuple(
                    UserConfiguration.from_document(dict(item)) for item in raw_users
                )
            ),
            profiles=ProfilesConfiguration(profiles=(administrator, *profiles)),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        ProfilesDefinitionError,
        UsersConfigurationValidationError,
    ) as error:
        raise UsersConfigurationValidationError(
            'Users/profiles schema v1 contract is invalid'
        ) from error
