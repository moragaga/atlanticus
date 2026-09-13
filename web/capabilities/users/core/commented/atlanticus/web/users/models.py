from __future__ import annotations

# Los modelos separan el usuario efectivo de los estados durables que puede resolver el runtime.
from dataclasses import dataclass

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.profiles import (
    GUEST_PROFILE_KEY,
    ProfileDefinition,
    normalize_profile_color,
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


# EffectiveUser representa al usuario utilizable durante una carga de página.
# Pending sigue siendo un estado operacional y por contrato siempre usa Guest.
@dataclass(frozen=True, slots=True)
class EffectiveUser:
    user_id: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    pending: bool
    avatar_text: str
    profile: ProfileDefinition
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
        if self.pending:
            if not self.enabled:
                raise UsersDefinitionError('Pending user must be enabled')
            if self.profile.key != GUEST_PROFILE_KEY:
                raise UsersDefinitionError('Pending user must use guest profile')
            if self.is_local:
                raise UsersDefinitionError('Pending user cannot be local')
        elif self.profile.key == GUEST_PROFILE_KEY:
            raise UsersDefinitionError('Guest profile is reserved for pending users')
        background = self.avatar_background_color or self.profile.background_color
        text = self.avatar_text_color or self.profile.text_color
        object.__setattr__(
            self,
            'avatar_background_color',
            normalize_profile_color(background),
        )
        object.__setattr__(self, 'avatar_text_color', normalize_profile_color(text))


# PendingUserRecord es el hecho durable de una identidad observada todavía no gestionada.
# No contiene perfil, enabled, permisos ni semántica específica de una aplicación.
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

    # Guest se materializa sólo al convertir Pending a usuario efectivo.
    def to_effective_user(self, *, profile: ProfileDefinition) -> EffectiveUser:
        if profile.key != GUEST_PROFILE_KEY:
            raise UsersDefinitionError('Pending user must use guest profile')
        display_name = self.display_name or self.email or 'Usuario pendiente'
        return EffectiveUser(
            user_id=self.user_id,
            subject_id=self.subject_id,
            display_name=display_name,
            email=self.email,
            enabled=True,
            pending=True,
            avatar_text=build_avatar_text(display_name),
            profile=profile,
            avatar_background_color=None,
            avatar_text_color=None,
            is_local=False,
        )


# ResolvedUserRecord representa ACTIVE o DISABLED ya gestionado.
# issuer + subject_id permanecen explícitos porque son la identidad autoritativa.
@dataclass(frozen=True, slots=True)
class ResolvedUserRecord:
    user_id: str
    issuer: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    profile_key: str
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
        profile_key = self.profile_key.strip().casefold()
        if not profile_key:
            raise UsersDefinitionError('Resolved user profile key must not be empty')
        if profile_key == GUEST_PROFILE_KEY:
            raise UsersDefinitionError('Resolved runtime user cannot use guest profile')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'email', _optional_text(self.email, casefold=True))
        object.__setattr__(self, 'profile_key', profile_key)
        if self.avatar_background_color is not None:
            object.__setattr__(
                self,
                'avatar_background_color',
                normalize_profile_color(self.avatar_background_color),
            )
        if self.avatar_text_color is not None:
            object.__setattr__(
                self,
                'avatar_text_color',
                normalize_profile_color(self.avatar_text_color),
            )

    # Managed se materializa con su perfil asignado y nunca como Pending.
    def to_effective_user(self, *, profile: ProfileDefinition) -> EffectiveUser:
        if profile.key != self.profile_key:
            raise UsersDefinitionError('Resolved profile does not match user profile key')
        return EffectiveUser(
            user_id=self.user_id,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=self.email,
            enabled=self.enabled,
            pending=False,
            avatar_text=build_avatar_text(self.display_name),
            profile=profile,
            avatar_background_color=self.avatar_background_color,
            avatar_text_color=self.avatar_text_color,
            is_local=self.is_local,
        )


# El runtime store sólo puede devolver uno de estos dos estados durables.
RuntimeUserRecord = PendingUserRecord | ResolvedUserRecord


def build_avatar_text(display_name: str) -> str:
    words = tuple(part for part in display_name.strip().split() if part)
    if not words:
        raise UsersDefinitionError('Display name must not be empty')
    if len(words) == 1:
        return words[0][:2].upper()
    return f'{words[0][0]}{words[-1][0]}'.upper()
