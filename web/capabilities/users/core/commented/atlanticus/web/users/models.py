from __future__ import annotations

# Contratos separados: identidad global, membership Tool y snapshot Runtime materializado.

from dataclasses import dataclass
from typing import Any

from atlanticus.web.profiles.models import (
    GUEST_PROFILE_KEY,
    ProfileDefinition,
    normalize_profile_color,
    normalize_profile_key,
)
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.profiles import has_full_access_profile, normalize_managed_profile_key


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
class UserIdentity:
    user_id: str
    issuer: str
    subject_id: str
    display_name: str
    email: str | None = None

    def __post_init__(self) -> None:
        issuer = _required_text(self.issuer, label='User issuer')
        subject_id = _required_text(self.subject_id, label='User subject id')
        user_id = _required_text(self.user_id, label='User id')
        display_name = _required_text(self.display_name, label='User display name')
        if user_id != build_user_key(issuer=issuer, subject_id=subject_id):
            raise UsersDefinitionError('User id must match authenticated identity')
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))

    def to_document(self) -> dict[str, object]:
        return {
            'user_id': self.user_id,
            'issuer': self.issuer,
            'subject_id': self.subject_id,
            'display_name': self.display_name,
            'email': self.email,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UserIdentity:
        try:
            return cls(
                user_id=_document_text(document, 'user_id'),
                issuer=_document_text(document, 'issuer'),
                subject_id=_document_text(document, 'subject_id'),
                display_name=_document_text(document, 'display_name'),
                email=_document_optional_text(document, 'email'),
            )
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('User identity contract is invalid') from error


@dataclass(frozen=True, slots=True)
class DiscoveredUser:
    issuer: str
    subject_id: str
    display_name: str | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'issuer', _required_text(self.issuer, label='User issuer'))
        object.__setattr__(
            self, 'subject_id', _required_text(self.subject_id, label='User subject id')
        )
        object.__setattr__(self, 'display_name', _optional_text(self.display_name))
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))

    @property
    def user_id(self) -> str:
        return build_user_key(issuer=self.issuer, subject_id=self.subject_id)

    def to_identity(
        self,
        *,
        display_name: str | None = None,
        email: str | None = None,
    ) -> UserIdentity:
        resolved_display_name = display_name or self.display_name or self.email
        if resolved_display_name is None:
            raise UsersDefinitionError('User display name must be provided')
        return UserIdentity(
            user_id=self.user_id,
            issuer=self.issuer,
            subject_id=self.subject_id,
            display_name=resolved_display_name,
            email=self.email if email is None else email,
        )


@dataclass(frozen=True, slots=True)
class UsersRegistrySnapshot:
    users: tuple[UserIdentity, ...] = ()
    version: str | None = None

    def __post_init__(self) -> None:
        users = tuple(self.users)
        if any(not isinstance(user, UserIdentity) for user in users):
            raise UsersDefinitionError('Users registry must contain UserIdentity entries')
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

    def get(self, user_id: str) -> UserIdentity | None:
        normalized = user_id.strip()
        return next((user for user in self.users if user.user_id == normalized), None)


@dataclass(frozen=True, slots=True)
class ToolUserMembership:
    user_id: str
    profile_key: str
    enabled: bool = True

    def __post_init__(self) -> None:
        user_id = _required_text(self.user_id, label='Membership user id')
        if not isinstance(self.enabled, bool):
            raise UsersDefinitionError('Membership enabled flag must be boolean')
        normalized_profile = normalize_managed_profile_key(self.profile_key)
        if normalized_profile == GUEST_PROFILE_KEY:
            raise UsersDefinitionError('Tool membership profile must not be guest')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'profile_key', normalized_profile)

    def to_document(self) -> dict[str, object]:
        return {
            'user_id': self.user_id,
            'profile_key': self.profile_key,
            'enabled': self.enabled,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> ToolUserMembership:
        try:
            enabled = document['enabled']
            if not isinstance(enabled, bool):
                raise TypeError
            return cls(
                user_id=_document_text(document, 'user_id'),
                profile_key=_document_text(document, 'profile_key'),
                enabled=enabled,
            )
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('Tool membership contract is invalid') from error


@dataclass(frozen=True, slots=True)
class ToolMembershipSnapshot:
    memberships: tuple[ToolUserMembership, ...] = ()
    version: str | None = None

    def __post_init__(self) -> None:
        memberships = tuple(self.memberships)
        if any(not isinstance(item, ToolUserMembership) for item in memberships):
            raise UsersDefinitionError('Membership registry contains invalid entries')
        user_ids = tuple(item.user_id for item in memberships)
        if len(user_ids) != len(set(user_ids)):
            raise UsersDefinitionError('Membership user ids must be unique')
        version = self.version
        if version is not None:
            version = version.strip()
            if not version:
                raise UsersDefinitionError('Membership registry version must not be empty')
        object.__setattr__(
            self,
            'memberships',
            tuple(sorted(memberships, key=lambda item: item.user_id)),
        )
        object.__setattr__(self, 'version', version)

    def get(self, user_id: str) -> ToolUserMembership | None:
        normalized = user_id.strip()
        return next(
            (membership for membership in self.memberships if membership.user_id == normalized),
            None,
        )


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    id: str
    label: str
    background_color: str
    text_color: str

    @classmethod
    def from_profile(cls, profile: ProfileDefinition) -> RuntimeProfile:
        if not isinstance(profile, ProfileDefinition):
            raise TypeError('Runtime profile requires ProfileDefinition')
        return cls(
            id=profile.key,
            label=profile.label,
            background_color=profile.background_color,
            text_color=profile.text_color,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'id': self.id,
            'label': self.label,
            'background_color': self.background_color,
            'text_color': self.text_color,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> RuntimeProfile:
        try:
            return cls(
                id=_document_text(document, 'id'),
                label=_document_text(document, 'label'),
                background_color=_document_text(document, 'background_color'),
                text_color=_document_text(document, 'text_color'),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersDefinitionError('Runtime profile contract is invalid') from error

    def __post_init__(self) -> None:
        object.__setattr__(self, 'id', normalize_profile_key(self.id))
        object.__setattr__(self, 'label', _required_text(self.label, label='Profile label'))
        try:
            object.__setattr__(
                self,
                'background_color',
                normalize_profile_color(self.background_color),
            )
            object.__setattr__(
                self,
                'text_color',
                normalize_profile_color(self.text_color),
            )
        except ValueError as error:
            raise UsersDefinitionError('Runtime profile color must use #RRGGBB') from error


@dataclass(frozen=True, slots=True)
class RuntimeOperationalReference:
    id: str | int
    label: str

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or not isinstance(self.id, (str, int)):
            raise UsersDefinitionError('Operational reference id is invalid')
        if isinstance(self.id, str) and not self.id.strip():
            raise UsersDefinitionError('Operational reference id must not be empty')
        object.__setattr__(self, 'label', _required_text(self.label, label='Operational label'))

    def to_document(self) -> dict[str, object]:
        return {'id': self.id, 'label': self.label}

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> RuntimeOperationalReference:
        try:
            identifier = document['id']
            if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
                raise TypeError
            return cls(id=identifier, label=_document_text(document, 'label'))
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('Operational reference contract is invalid') from error


@dataclass(frozen=True, slots=True)
class RuntimeOperational:
    area: RuntimeOperationalReference | None = None
    position: RuntimeOperationalReference | None = None
    group: RuntimeOperationalReference | None = None

    def to_document(self) -> dict[str, object]:
        return {
            'area': None if self.area is None else self.area.to_document(),
            'position': None if self.position is None else self.position.to_document(),
            'group': None if self.group is None else self.group.to_document(),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> RuntimeOperational:
        if not isinstance(document, dict) or set(document) != {'area', 'position', 'group'}:
            raise UsersDefinitionError('Runtime operational contract is invalid')
        try:
            return cls(
                area=_reference_from_document(document.get('area')),
                position=_reference_from_document(document.get('position')),
                group=_reference_from_document(document.get('group')),
            )
        except (TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('Runtime operational contract is invalid') from error


@dataclass(frozen=True, slots=True)
class RuntimeUser:
    identity: UserIdentity
    enabled: bool
    profile: RuntimeProfile
    operational: RuntimeOperational = RuntimeOperational()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, UserIdentity):
            raise TypeError('Runtime user identity must be UserIdentity')
        if not isinstance(self.enabled, bool):
            raise UsersDefinitionError('Runtime user enabled flag must be boolean')
        if not isinstance(self.profile, RuntimeProfile):
            raise TypeError('Runtime user profile must be RuntimeProfile')
        if not isinstance(self.operational, RuntimeOperational):
            raise TypeError('Runtime user operational data must be RuntimeOperational')

    @property
    def user_id(self) -> str:
        return self.identity.user_id

    @property
    def issuer(self) -> str:
        return self.identity.issuer

    @property
    def subject_id(self) -> str:
        return self.identity.subject_id

    @property
    def display_name(self) -> str:
        return self.identity.display_name

    @property
    def email(self) -> str | None:
        return self.identity.email

    @property
    def has_full_access(self) -> bool:
        return has_full_access_profile(self.profile.id)

    def to_document(self) -> dict[str, object]:
        return {
            'identity': self.identity.to_document(),
            'enabled': self.enabled,
            'profile': self.profile.to_document(),
            'operational': self.operational.to_document(),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> RuntimeUser:
        try:
            identity = document['identity']
            profile = document['profile']
            operational = document['operational']
            enabled = document['enabled']
            if not all(isinstance(value, dict) for value in (identity, profile, operational)):
                raise TypeError
            if not isinstance(enabled, bool):
                raise TypeError
            return cls(
                identity=UserIdentity.from_document(identity),
                enabled=enabled,
                profile=RuntimeProfile.from_document(profile),
                operational=RuntimeOperational.from_document(operational),
            )
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('Runtime user contract is invalid') from error


@dataclass(frozen=True, slots=True)
class ManagedUser:
    identity: UserIdentity
    membership: ToolUserMembership

    def __post_init__(self) -> None:
        if self.identity.user_id != self.membership.user_id:
            raise UsersDefinitionError('Managed user identity and membership do not match')

    @property
    def user_id(self) -> str:
        return self.identity.user_id

    @property
    def display_name(self) -> str:
        return self.identity.display_name

    @property
    def email(self) -> str | None:
        return self.identity.email

    @property
    def profile_key(self) -> str:
        return self.membership.profile_key

    @property
    def enabled(self) -> bool:
        return self.membership.enabled

    def to_document(self) -> dict[str, object]:
        return {
            **self.identity.to_document(),
            'profile_key': self.profile_key,
            'enabled': self.enabled,
        }


def build_runtime_user(
    *,
    identity: UserIdentity,
    membership: ToolUserMembership,
    profile: ProfileDefinition,
    operational: RuntimeOperational | None = None,
) -> RuntimeUser:
    if identity.user_id != membership.user_id:
        raise UsersDefinitionError('Runtime user identity and membership do not match')
    if normalize_managed_profile_key(membership.profile_key) != profile.key:
        raise UsersDefinitionError('Runtime user profile does not match membership')
    return RuntimeUser(
        identity=identity,
        enabled=membership.enabled,
        profile=RuntimeProfile.from_profile(profile),
        operational=operational or RuntimeOperational(),
    )


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


def _reference_from_document(value: object) -> RuntimeOperationalReference | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError
    return RuntimeOperationalReference.from_document(value)
