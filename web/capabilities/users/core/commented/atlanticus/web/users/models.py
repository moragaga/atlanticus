from __future__ import annotations

# El usuario efectivo transporta authority_key, no objetos ProfileDefinition.
# Pending materializa guest; un usuario resuelto materializa directamente su autoridad runtime.
# local queda reservado a registros marcados explícitamente como runtime local.


from dataclasses import dataclass

from atlanticus.web.users.authority import (
    GUEST_AUTHORITY_KEY,
    GUEST_BACKGROUND_COLOR,
    GUEST_TEXT_COLOR,
    LOCAL_AUTHORITY_KEY,
    has_full_access,
    normalize_authority_key,
    normalize_user_color,
)
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key


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
class EffectiveUser:
    user_id: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    pending: bool
    avatar_text: str
    authority_key: str
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None
    is_local: bool = False

    def __post_init__(self) -> None:
        for field_name in ('user_id', 'subject_id', 'display_name', 'avatar_text'):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise UsersDefinitionError(f'Effective user {field_name} must not be empty')
            object.__setattr__(self, field_name, value)
        if self.email is not None:
            email = self.email.strip().casefold()
            object.__setattr__(self, 'email', email or None)
        authority_key = normalize_authority_key(self.authority_key)
        object.__setattr__(self, 'authority_key', authority_key)
        if self.pending:
            if not self.enabled:
                raise UsersDefinitionError('Pending user must be enabled')
            if authority_key != GUEST_AUTHORITY_KEY:
                raise UsersDefinitionError('Pending user must use guest authority')
            if self.is_local:
                raise UsersDefinitionError('Pending user cannot be local')
            if self.avatar_background_color is not None or self.avatar_text_color is not None:
                raise UsersDefinitionError('Pending user avatar colors are fixed')
            object.__setattr__(self, 'avatar_background_color', GUEST_BACKGROUND_COLOR)
            object.__setattr__(self, 'avatar_text_color', GUEST_TEXT_COLOR)
            return
        if authority_key == GUEST_AUTHORITY_KEY:
            raise UsersDefinitionError('Resolved user cannot use guest authority')
        if self.is_local and authority_key != LOCAL_AUTHORITY_KEY:
            raise UsersDefinitionError('Local user must use local authority')
        if not self.is_local and authority_key == LOCAL_AUTHORITY_KEY:
            raise UsersDefinitionError('Managed user cannot use local authority')
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
        return has_full_access(self.authority_key)


@dataclass(frozen=True, slots=True)
class PendingUserRecord:
    user_id: str
    issuer: str
    subject_id: str
    display_name: str | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        issuer = _required_text(self.issuer, label='Pending user issuer')
        subject_id = _required_text(self.subject_id, label='Pending user subject id')
        user_id = _required_text(self.user_id, label='Pending user id')
        expected_user_id = build_user_key(issuer=issuer, subject_id=subject_id)
        if user_id != expected_user_id:
            raise UsersDefinitionError('Pending user id must match authenticated identity')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)
        object.__setattr__(self, 'display_name', _optional_text(self.display_name))
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))

    def to_effective_user(self) -> EffectiveUser:
        display_name = self.display_name or self.email or 'Usuario pendiente'
        return EffectiveUser(
            user_id=self.user_id,
            subject_id=self.subject_id,
            display_name=display_name,
            email=self.email,
            enabled=True,
            pending=True,
            avatar_text=build_avatar_text(display_name),
            authority_key=GUEST_AUTHORITY_KEY,
            avatar_background_color=None,
            avatar_text_color=None,
            is_local=False,
        )


@dataclass(frozen=True, slots=True)
class ResolvedUserRecord:
    user_id: str
    issuer: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    authority_key: str
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None
    is_local: bool = False

    def __post_init__(self) -> None:
        issuer = _required_text(self.issuer, label='Resolved user issuer')
        subject_id = _required_text(self.subject_id, label='Resolved user subject id')
        user_id = _required_text(self.user_id, label='Resolved user id')
        display_name = _required_text(self.display_name, label='Resolved user display name')
        expected_user_id = build_user_key(issuer=issuer, subject_id=subject_id)
        if user_id != expected_user_id:
            raise UsersDefinitionError('Resolved user id must match authenticated identity')
        if not isinstance(self.enabled, bool):
            raise UsersDefinitionError('Resolved user enabled flag must be boolean')
        authority_key = normalize_authority_key(self.authority_key)
        if authority_key == GUEST_AUTHORITY_KEY:
            raise UsersDefinitionError('Resolved runtime user cannot use guest authority')
        if self.is_local and authority_key != LOCAL_AUTHORITY_KEY:
            raise UsersDefinitionError('Local runtime user must use local authority')
        if not self.is_local and authority_key == LOCAL_AUTHORITY_KEY:
            raise UsersDefinitionError('Managed runtime user cannot use local authority')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))
        object.__setattr__(self, 'authority_key', authority_key)
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
            pending=False,
            avatar_text=build_avatar_text(self.display_name),
            authority_key=self.authority_key,
            avatar_background_color=self.avatar_background_color,
            avatar_text_color=self.avatar_text_color,
            is_local=self.is_local,
        )


RuntimeUserRecord = PendingUserRecord | ResolvedUserRecord


def build_avatar_text(display_name: str) -> str:
    words = tuple(part for part in display_name.strip().split() if part)
    if not words:
        raise UsersDefinitionError('Display name must not be empty')
    if len(words) == 1:
        return words[0][:2].upper()
    return f'{words[0][0]}{words[-1][0]}'.upper()
