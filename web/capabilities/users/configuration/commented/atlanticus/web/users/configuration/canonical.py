from __future__ import annotations

# Este módulo contiene los contratos canónicos separados de Users y la composición Users→Profiles.
from dataclasses import dataclass
from typing import Any

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.configuration.models import UserConfiguration, UsersConfigurationCatalog

_ADMINISTRATOR_PROFILE_KEY = 'administrator'
_NON_FUNCTIONAL_PROFILE_KEYS = frozenset({'guest', 'local'})


# Users conserva únicamente Managed Users y sus invariantes propias; no posee el catálogo de Profiles.
@dataclass(frozen=True, slots=True)
class UsersConfiguration:
    users: tuple[UserConfiguration, ...] = ()

    def __post_init__(self) -> None:
        users = tuple(self.users)
        user_ids = tuple(user.user_id for user in users)
        if len(user_ids) != len(set(user_ids)):
            raise UsersConfigurationValidationError('User ids must be unique')
        emails = tuple(user.email for user in users if user.email is not None)
        if len(emails) != len(set(emails)):
            raise UsersConfigurationValidationError('User emails must be unique')
        identities = tuple((user.issuer, user.subject_id) for user in users)
        if len(identities) != len(set(identities)):
            raise UsersConfigurationValidationError('User identities must be unique')
        object.__setattr__(self, 'users', users)

    def to_document(self) -> dict[str, object]:
        return {'users': [user.to_document() for user in self.users]}

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersConfiguration:
        try:
            raw_users = document['users']
            if not isinstance(raw_users, list) or not all(isinstance(item, dict) for item in raw_users):
                raise TypeError
            return cls(
                users=tuple(UserConfiguration.from_document(dict(item)) for item in raw_users)
            )
        except (KeyError, TypeError, ValueError, UsersConfigurationValidationError) as error:
            raise UsersConfigurationValidationError('Users configuration contract is invalid') from error


# La composición valida referencias entre contratos sin devolver ownership de Profiles a Users.
@dataclass(frozen=True, slots=True)
class UsersProfilesConfiguration:
    users: UsersConfiguration
    profiles: ProfilesConfiguration

    def __post_init__(self) -> None:
        catalog = self.profiles.catalog()
        profile_keys = {profile.key for profile in catalog.all()}
        unsupported = profile_keys.intersection(_NON_FUNCTIONAL_PROFILE_KEYS)
        if unsupported:
            raise UsersConfigurationValidationError(
                'Guest and local profiles cannot be configured as functional profiles'
            )
        try:
            catalog.require(_ADMINISTRATOR_PROFILE_KEY)
            for user in self.users.users:
                catalog.require(user.profile_key)
        except ProfilesDefinitionError as error:
            raise UsersConfigurationValidationError(str(error)) from error

    # El catálogo funcional se obtiene desde el contrato Profiles-owned ya validado.
    def profile_catalog(self) -> ProfileCatalog:
        return self.profiles.catalog()

    def to_document(self) -> dict[str, object]:
        return {
            'users': list(self.users.to_document()['users']),
            'profiles': list(self.profiles.to_document()['profiles']),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersProfilesConfiguration:
        try:
            raw_users = document['users']
            raw_profiles = document['profiles']
            if not isinstance(raw_users, list) or not isinstance(raw_profiles, list):
                raise TypeError
            return cls(
                users=UsersConfiguration.from_document({'users': list(raw_users)}),
                profiles=ProfilesConfiguration.from_document({'profiles': list(raw_profiles)}),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            ProfilesDefinitionError,
            UsersConfigurationValidationError,
        ) as error:
            raise UsersConfigurationValidationError(
                'Users/profiles configuration contract is invalid'
            ) from error


# El reader histórico normaliza el schema previo hacia los contratos nuevos; no se usa para escribir releases nuevas.
def split_legacy_users_configuration_catalog(
    catalog: UsersConfigurationCatalog,
) -> UsersProfilesConfiguration:
    administrator = ProfileDefinition(
        key=_ADMINISTRATOR_PROFILE_KEY,
        label='Administrador',
        background_color=catalog.administrator_background_color,
        text_color=catalog.administrator_text_color,
    )
    return UsersProfilesConfiguration(
        users=UsersConfiguration(users=catalog.users),
        profiles=ProfilesConfiguration(
            profiles=(
                administrator,
                *(profile.to_profile_definition() for profile in catalog.profiles),
            )
        ),
    )
