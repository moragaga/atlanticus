# Espejo pedagógico del módulo productivo.
# Los comentarios explican responsabilidades sin alterar estructura ni comportamiento.
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.profiles import (
    ADMINISTRATOR_PROFILE_KEY,
    DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
    DEFAULT_ADMINISTRATOR_TEXT_COLOR,
    DEFAULT_GUEST_BACKGROUND_COLOR,
    DEFAULT_GUEST_TEXT_COLOR,
    GUEST_PROFILE_KEY,
    LOCAL_PROFILE_KEY,
    ProfileCatalog,
    ProfileDefinition,
    normalize_profile_color,
    normalize_profile_key,
)

_RESERVED_PROFILE_KEYS = frozenset(
    {LOCAL_PROFILE_KEY, ADMINISTRATOR_PROFILE_KEY, GUEST_PROFILE_KEY}
)
_PROFILE_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_NON_KEY_PATTERN = re.compile(r'[^a-z0-9]+')


# Encapsula la operación required para mantener esta responsabilidad aislada.
def _required(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise UsersConfigurationValidationError(f'{label} must not be empty')
    return normalized


# Encapsula la operación optional para mantener esta responsabilidad aislada.
def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


# Encapsula la operación build profile key para mantener esta responsabilidad aislada.
def build_profile_key(label: str) -> str:
    normalized = unicodedata.normalize('NFKD', label.strip())
    ascii_text = ''.join(
        character for character in normalized if not unicodedata.combining(character)
    )
    candidate = _NON_KEY_PATTERN.sub('_', ascii_text.casefold()).strip('_')
    if not _PROFILE_KEY_PATTERN.fullmatch(candidate):
        raise UsersConfigurationValidationError('Generated profile key has an invalid format')
    if candidate in _RESERVED_PROFILE_KEYS:
        raise UsersConfigurationValidationError('Generated profile key is reserved')
    return candidate


# Encapsula la operación normalize email para mantener esta responsabilidad aislada.
def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or '@' not in normalized:
        raise UsersConfigurationValidationError('User email is invalid')
    return normalized


# Encapsula la operación build user key para mantener esta responsabilidad aislada.
def build_user_key(*, issuer: str | None, subject_id: str | None, email: str) -> str:
    identity = f'{issuer}|{subject_id}' if issuer and subject_id else normalize_email(email)
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
    return f'user:{digest}'


# Define UserProfileConfiguration como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UserProfileConfiguration:
    key: str
    label: str
    background_color: str
    text_color: str = '#FFFFFF'

    def __post_init__(self) -> None:
        key = normalize_profile_key(self.key)
        if key in _RESERVED_PROFILE_KEYS:
            raise UsersConfigurationValidationError('System profiles cannot be redefined')
        label = _required(self.label, label='Profile label')
        background_color = normalize_profile_color(self.background_color)
        text_color = normalize_profile_color(self.text_color)
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'background_color', background_color)
        object.__setattr__(self, 'text_color', text_color)

    def to_profile_definition(self) -> ProfileDefinition:
        return ProfileDefinition(
            key=self.key,
            label=self.label,
            background_color=self.background_color,
            text_color=self.text_color,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'key': self.key,
            'label': self.label,
            'background_color': self.background_color,
            'text_color': self.text_color,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UserProfileConfiguration:
        try:
            return cls(
                key=str(document['key']),
                label=str(document['label']),
                background_color=str(document['background_color']),
                text_color=str(document['text_color']),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError('Profile contract is invalid') from error


# Define UserConfiguration como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UserConfiguration:
    user_id: str
    display_name: str
    email: str
    profile_key: str
    enabled: bool = True
    issuer: str | None = None
    subject_id: str | None = None

    def __post_init__(self) -> None:
        issuer = _optional(self.issuer)
        subject_id = _optional(self.subject_id)
        if (issuer is None) != (subject_id is None):
            raise UsersConfigurationValidationError('User issuer and subject id must coexist')
        display_name = _required(self.display_name, label='User display name')
        email = normalize_email(self.email)
        profile_key = normalize_profile_key(self.profile_key)
        if profile_key == LOCAL_PROFILE_KEY:
            raise UsersConfigurationValidationError('Local profile cannot be assigned')
        if not isinstance(self.enabled, bool):
            raise UsersConfigurationValidationError('User enabled flag must be boolean')
        expected_user_id = build_user_key(
            issuer=issuer,
            subject_id=subject_id,
            email=email,
        )
        user_id = self.user_id.strip() or expected_user_id
        if not user_id:
            raise UsersConfigurationValidationError('User id must not be empty')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'email', email)
        object.__setattr__(self, 'profile_key', profile_key)
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)

    @classmethod
    def create(
        cls,
        *,
        display_name: str,
        email: str,
        profile_key: str,
        enabled: bool = True,
        issuer: str | None = None,
        subject_id: str | None = None,
        user_id: str | None = None,
    ) -> UserConfiguration:
        return cls(
            user_id=user_id
            or build_user_key(issuer=issuer, subject_id=subject_id, email=email),
            display_name=display_name,
            email=email,
            profile_key=profile_key,
            enabled=enabled,
            issuer=issuer,
            subject_id=subject_id,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'user_id': self.user_id,
            'display_name': self.display_name,
            'email': self.email,
            'profile_key': self.profile_key,
            'enabled': self.enabled,
            'issuer': self.issuer,
            'subject_id': self.subject_id,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UserConfiguration:
        try:
            enabled = document.get('enabled', True)
            if not isinstance(enabled, bool):
                raise TypeError
            return cls(
                user_id=str(document['user_id']),
                display_name=str(document['display_name']),
                email=str(document['email']),
                profile_key=str(document['profile_key']),
                enabled=enabled,
                issuer=_optional_value(document.get('issuer')),
                subject_id=_optional_value(document.get('subject_id')),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError('User contract is invalid') from error


# Define DiscoveredUser como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class DiscoveredUser:
    user_id: str
    issuer: str
    subject_id: str
    display_name: str
    email: str

    def __post_init__(self) -> None:
        object.__setattr__(self, 'user_id', _required(self.user_id, label='Discovered user id'))
        object.__setattr__(self, 'issuer', _required(self.issuer, label='Discovered user issuer'))
        object.__setattr__(
            self,
            'subject_id',
            _required(self.subject_id, label='Discovered user subject id'),
        )
        object.__setattr__(
            self,
            'display_name',
            _required(self.display_name, label='Discovered user display name'),
        )
        object.__setattr__(self, 'email', normalize_email(self.email))

    def to_configuration(self, *, profile_key: str) -> UserConfiguration:
        return UserConfiguration.create(
            user_id=self.user_id,
            issuer=self.issuer,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=self.email,
            profile_key=profile_key,
        )


# Define UsersConfigurationCatalog como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UsersConfigurationCatalog:
    administrator_background_color: str = DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR
    administrator_text_color: str = DEFAULT_ADMINISTRATOR_TEXT_COLOR
    guest_background_color: str = DEFAULT_GUEST_BACKGROUND_COLOR
    guest_text_color: str = DEFAULT_GUEST_TEXT_COLOR
    profiles: tuple[UserProfileConfiguration, ...] = ()
    users: tuple[UserConfiguration, ...] = ()

    def __post_init__(self) -> None:
        administrator_background_color = normalize_profile_color(
            self.administrator_background_color
        )
        administrator_text_color = normalize_profile_color(self.administrator_text_color)
        guest_background_color = normalize_profile_color(self.guest_background_color)
        guest_text_color = normalize_profile_color(self.guest_text_color)
        profiles = tuple(self.profiles)
        users = tuple(self.users)
        profile_keys = tuple(profile.key for profile in profiles)
        if len(profile_keys) != len(set(profile_keys)):
            raise UsersConfigurationValidationError('Profile keys must be unique')
        user_ids = tuple(user.user_id for user in users)
        if len(user_ids) != len(set(user_ids)):
            raise UsersConfigurationValidationError('User ids must be unique')
        emails = tuple(user.email for user in users)
        if len(emails) != len(set(emails)):
            raise UsersConfigurationValidationError('User emails must be unique')
        identities = tuple(
            (user.issuer, user.subject_id)
            for user in users
            if user.issuer is not None and user.subject_id is not None
        )
        if len(identities) != len(set(identities)):
            raise UsersConfigurationValidationError('User identities must be unique')
        catalog = ProfileCatalog(
            administrator_background_color=administrator_background_color,
            administrator_text_color=administrator_text_color,
            guest_background_color=guest_background_color,
            guest_text_color=guest_text_color,
            custom_profiles=tuple(profile.to_profile_definition() for profile in profiles),
        )
        for user in users:
            catalog.require(user.profile_key)
        object.__setattr__(
            self,
            'administrator_background_color',
            administrator_background_color,
        )
        object.__setattr__(self, 'administrator_text_color', administrator_text_color)
        object.__setattr__(self, 'guest_background_color', guest_background_color)
        object.__setattr__(self, 'guest_text_color', guest_text_color)
        object.__setattr__(self, 'profiles', profiles)
        object.__setattr__(self, 'users', users)

    def profile_catalog(self) -> ProfileCatalog:
        return ProfileCatalog(
            administrator_background_color=self.administrator_background_color,
            administrator_text_color=self.administrator_text_color,
            guest_background_color=self.guest_background_color,
            guest_text_color=self.guest_text_color,
            custom_profiles=tuple(profile.to_profile_definition() for profile in self.profiles),
        )

    def to_document(self) -> dict[str, object]:
        return {
            'administrator_background_color': self.administrator_background_color,
            'administrator_text_color': self.administrator_text_color,
            'guest_background_color': self.guest_background_color,
            'guest_text_color': self.guest_text_color,
            'profiles': [profile.to_document() for profile in self.profiles],
            'users': [user.to_document() for user in self.users],
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersConfigurationCatalog:
        try:
            profiles = document.get('profiles', [])
            users = document.get('users', [])
            if not isinstance(profiles, list) or not all(
                isinstance(item, dict) for item in profiles
            ):
                raise TypeError
            if not isinstance(users, list) or not all(isinstance(item, dict) for item in users):
                raise TypeError
            return cls(
                administrator_background_color=str(
                    document['administrator_background_color']
                ),
                administrator_text_color=str(document['administrator_text_color']),
                guest_background_color=str(document['guest_background_color']),
                guest_text_color=str(document['guest_text_color']),
                profiles=tuple(
                    UserProfileConfiguration.from_document(dict(item)) for item in profiles
                ),
                users=tuple(UserConfiguration.from_document(dict(item)) for item in users),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError(
                'Users configuration contract is invalid'
            ) from error


# Encapsula la operación optional value para mantener esta responsabilidad aislada.
def _optional_value(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
