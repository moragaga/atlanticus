from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import normalize_profile_key
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.identity import build_user_key

_LOCAL_PROFILE_KEY = 'local'
_ADMINISTRATOR_PROFILE_KEY = 'administrator'
_GUEST_PROFILE_KEY = 'guest'
_RESERVED_PROFILE_KEYS = frozenset(
    {_LOCAL_PROFILE_KEY, _ADMINISTRATOR_PROFILE_KEY, _GUEST_PROFILE_KEY}
)
_PROFILE_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_NON_KEY_PATTERN = re.compile(r'[^a-z0-9]+')
_T = TypeVar('_T')


def _profile_value(factory: Callable[[], _T]) -> _T:
    try:
        return factory()
    except ProfilesDefinitionError as error:
        raise UsersConfigurationValidationError(str(error)) from error


def _required(value: str | None, *, label: str) -> str:
    if value is None:
        raise UsersConfigurationValidationError(f'{label} must not be empty')
    normalized = value.strip()
    if not normalized:
        raise UsersConfigurationValidationError(f'{label} must not be empty')
    return normalized


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


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if not normalized:
        return None
    if '@' not in normalized:
        raise UsersConfigurationValidationError('User email is invalid')
    return normalized


@dataclass(frozen=True, slots=True)
class UserConfiguration:
    user_id: str
    display_name: str
    email: str | None
    profile_key: str
    enabled: bool = True
    issuer: str | None = None
    subject_id: str | None = None

    def __post_init__(self) -> None:
        issuer = _required(self.issuer, label='User issuer')
        subject_id = _required(self.subject_id, label='User subject id')
        display_name = _required(self.display_name, label='User display name')
        email = normalize_email(self.email)
        profile_key = _profile_value(lambda: normalize_profile_key(self.profile_key))
        if profile_key in {_LOCAL_PROFILE_KEY, _GUEST_PROFILE_KEY}:
            raise UsersConfigurationValidationError(
                'Guest and local profiles cannot be assigned to managed users'
            )
        if not isinstance(self.enabled, bool):
            raise UsersConfigurationValidationError('User enabled flag must be boolean')
        expected_user_id = build_user_key(issuer=issuer, subject_id=subject_id)
        user_id = self.user_id.strip() or expected_user_id
        if user_id != expected_user_id:
            raise UsersConfigurationValidationError('User id must match authenticated identity')
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
        profile_key: str,
        email: str | None = None,
        enabled: bool = True,
        issuer: str | None = None,
        subject_id: str | None = None,
        user_id: str | None = None,
    ) -> UserConfiguration:
        return cls(
            user_id=user_id or '',
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
                email=_optional_document_string(document, 'email'),
                profile_key=str(document['profile_key']),
                enabled=enabled,
                issuer=_required_document_string(document, 'issuer'),
                subject_id=_required_document_string(document, 'subject_id'),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError('User contract is invalid') from error


def _required_document_string(document: dict[str, Any], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_document_string(document: dict[str, Any], key: str) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError
    return value
