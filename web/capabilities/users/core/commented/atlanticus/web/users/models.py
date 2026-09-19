from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import LOCAL_PROFILE_KEY, normalize_profile_key
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.profiles import (
    has_full_access_profile,
    normalize_managed_profile_key,
)


def _required_text(value: str | None, *, label: str) -> str:
    if value is None:
        raise UsersDefinitionError(f'{label} must not be empty')
    normalized = value.strip()
    if not normalized:
        raise UsersDefinitionError(f'{label} must not be empty')
    return normalized


def _optional_text(value: str | None, *, casefold: bool = False) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.casefold() if casefold else normalized


@dataclass(frozen=True, slots=True)
# Registro durable: Users persiste sólo la key; metadata y permisos permanecen en Profiles/Access.
class UserRecord:
    user_id: str
    issuer: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    profile_key: str
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None

    def __post_init__(self) -> None:
        issuer = _required_text(self.issuer, label='User issuer')
        subject_id = _required_text(self.subject_id, label='User subject id')
        user_id = _required_text(self.user_id, label='User id')
        display_name = _required_text(self.display_name, label='User display name')
        expected_user_id = build_user_key(issuer=issuer, subject_id=subject_id)
        if user_id != expected_user_id:
            raise UsersDefinitionError('User id must match authenticated identity')
        if not isinstance(self.enabled, bool):
            raise UsersDefinitionError('User enabled flag must be boolean')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))
        object.__setattr__(self, 'profile_key', normalize_managed_profile_key(self.profile_key))
        if self.avatar_background_color is not None:
            object.__setattr__(
                self,
                'avatar_background_color',
                normalize_user_color(self.avatar_background_color),
            )
        if self.avatar_text_color is not None:
            object.__setattr__(
                self,
                'avatar_text_color',
                normalize_user_color(self.avatar_text_color),
            )

    def to_effective_user(self) -> EffectiveUser:
        return EffectiveUser(
            user_id=self.user_id,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=self.email,
            enabled=self.enabled,
            avatar_text=build_avatar_text(self.display_name),
            profile_key=self.profile_key,
            avatar_background_color=self.avatar_background_color,
            avatar_text_color=self.avatar_text_color,
            is_local=False,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'user_id': self.user_id,
            'issuer': self.issuer,
            'subject_id': self.subject_id,
            'display_name': self.display_name,
            'email': self.email,
            'enabled': self.enabled,
            'profile_key': self.profile_key,
            'avatar_background_color': self.avatar_background_color,
            'avatar_text_color': self.avatar_text_color,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UserRecord:
        try:
            enabled = document['enabled']
            if not isinstance(enabled, bool):
                raise TypeError
            return cls(
                user_id=_document_text(document, 'user_id'),
                issuer=_document_text(document, 'issuer'),
                subject_id=_document_text(document, 'subject_id'),
                display_name=_document_text(document, 'display_name'),
                email=_document_optional_text(document, 'email'),
                enabled=enabled,
                profile_key=_document_text(document, 'profile_key'),
                avatar_background_color=_document_optional_text(
                    document,
                    'avatar_background_color',
                ),
                avatar_text_color=_document_optional_text(document, 'avatar_text_color'),
            )
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('User record contract is invalid') from error


@dataclass(frozen=True, slots=True)
class DiscoveredUser:
    issuer: str
    subject_id: str
    display_name: str | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'issuer', _required_text(self.issuer, label='User issuer'))
        object.__setattr__(
            self,
            'subject_id',
            _required_text(self.subject_id, label='User subject id'),
        )
        object.__setattr__(self, 'display_name', _optional_text(self.display_name))
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))

    @property
    def user_id(self) -> str:
        return build_user_key(issuer=self.issuer, subject_id=self.subject_id)

    def promote_as(
        self,
        *,
        profile_key: str,
        display_name: str | None = None,
        email: str | None = None,
        enabled: bool = True,
    ) -> UserRecord:
        resolved_display_name = display_name or self.display_name or self.email
        if resolved_display_name is None:
            raise UsersDefinitionError('Promoted user display name must be provided')
        return UserRecord(
            user_id=self.user_id,
            issuer=self.issuer,
            subject_id=self.subject_id,
            display_name=resolved_display_name,
            email=self.email if email is None else email,
            enabled=enabled,
            profile_key=profile_key,
        )


@dataclass(frozen=True, slots=True)
class UsersRegistrySnapshot:
    users: tuple[UserRecord, ...] = ()
    version: str | None = None

    def __post_init__(self) -> None:
        users = tuple(self.users)
        user_ids = tuple(user.user_id for user in users)
        identities = tuple((user.issuer, user.subject_id) for user in users)
        if len(user_ids) != len(set(user_ids)):
            raise UsersDefinitionError('User ids must be unique in users registry')
        if len(identities) != len(set(identities)):
            raise UsersDefinitionError('User identities must be unique in users registry')
        version = self.version
        if version is not None:
            version = version.strip()
            if not version:
                raise UsersDefinitionError('Users registry version must not be empty')
        object.__setattr__(self, 'users', tuple(sorted(users, key=lambda user: user.user_id)))
        object.__setattr__(self, 'version', version)

    def get(self, user_id: str) -> UserRecord | None:
        normalized = user_id.strip()
        return next((user for user in self.users if user.user_id == normalized), None)


@dataclass(frozen=True, slots=True)
# Usuario efectivo de request: conserva la profile_key y el caso local explícito.
class EffectiveUser:
    user_id: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    avatar_text: str
    profile_key: str
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None
    is_local: bool = False

    def __post_init__(self) -> None:
        for field_name in ('user_id', 'subject_id', 'display_name', 'avatar_text'):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise UsersDefinitionError(f'Effective user {field_name} must not be empty')
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))
        if not isinstance(self.enabled, bool):
            raise UsersDefinitionError('Effective user enabled flag must be boolean')
        if not isinstance(self.is_local, bool):
            raise UsersDefinitionError('Effective user local flag must be boolean')
        if self.is_local:
            try:
                profile_key = normalize_profile_key(self.profile_key)
            except ProfilesDefinitionError as error:
                raise UsersDefinitionError('Local user profile key is invalid') from error
            if profile_key != LOCAL_PROFILE_KEY:
                raise UsersDefinitionError('Local user must use local profile')
        else:
            profile_key = normalize_managed_profile_key(self.profile_key)
        object.__setattr__(self, 'profile_key', profile_key)
        if self.avatar_background_color is not None:
            object.__setattr__(
                self,
                'avatar_background_color',
                normalize_user_color(self.avatar_background_color),
            )
        if self.avatar_text_color is not None:
            object.__setattr__(
                self,
                'avatar_text_color',
                normalize_user_color(self.avatar_text_color),
            )

    @property
    def has_full_access(self) -> bool:
        return has_full_access_profile(self.profile_key)


def normalize_user_color(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 7 or normalized[0] != '#':
        raise UsersDefinitionError('User color must use #RRGGBB format')
    if any(character not in '0123456789ABCDEF' for character in normalized[1:]):
        raise UsersDefinitionError('User color must use #RRGGBB format')
    return normalized


def build_avatar_text(display_name: str) -> str:
    words = tuple(part for part in display_name.strip().split() if part)
    if not words:
        raise UsersDefinitionError('Display name must not be empty')
    if len(words) == 1:
        return words[0][:2].upper()
    return f'{words[0][0]}{words[-1][0]}'.upper()


def _document_text(document: dict[str, Any], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _document_optional_text(document: dict[str, Any], key: str) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError
    return value
