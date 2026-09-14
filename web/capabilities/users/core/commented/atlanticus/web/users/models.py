from __future__ import annotations

from dataclasses import dataclass

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileDefinition, normalize_profile_color
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key

# Guest es una semántica de Users para Pending; no es un Profile del dominio Profiles.
_GUEST_PROFILE_KEY = 'guest'
# La identidad Pending usa presentación estática propia de Users y no depende de configuración proyectada.
_PENDING_USER_BACKGROUND_COLOR = '#FF5722'
_PENDING_USER_TEXT_COLOR = '#FFFFFF'


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


def _user_profile_color(value: str) -> str:
    try:
        return normalize_profile_color(value)
    except ProfilesDefinitionError as error:
        raise UsersDefinitionError(str(error)) from error


@dataclass(frozen=True, slots=True)
# EffectiveUser representa el estado efectivo de acceso: Pending no tiene Profile; Managed sí.
class EffectiveUser:
    user_id: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    pending: bool
    avatar_text: str
    profile: ProfileDefinition | None
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
        # Pending mantiene una invariante estricta y no puede recibir Profile ni colores configurables.
        if self.pending:
            if not self.enabled:
                raise UsersDefinitionError('Pending user must be enabled')
            if self.profile is not None:
                raise UsersDefinitionError('Pending user must not have a profile')
            if self.is_local:
                raise UsersDefinitionError('Pending user cannot be local')
            if self.avatar_background_color is not None or self.avatar_text_color is not None:
                raise UsersDefinitionError('Pending user avatar colors are fixed')
            background = _PENDING_USER_BACKGROUND_COLOR
            text = _PENDING_USER_TEXT_COLOR
        else:
            # Todo usuario resuelto debe apuntar a un Profile funcional ya disponible en el catálogo runtime.
            if self.profile is None:
                raise UsersDefinitionError('Resolved user must have a profile')
            if self.profile.key == _GUEST_PROFILE_KEY:
                raise UsersDefinitionError('Resolved user cannot use guest profile key')
            background = self.avatar_background_color or self.profile.background_color
            text = self.avatar_text_color or self.profile.text_color
        object.__setattr__(self, 'avatar_background_color', _user_profile_color(background))
        object.__setattr__(self, 'avatar_text_color', _user_profile_color(text))


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

    # Materializar Pending no consulta Profiles: sólo deriva nombre, avatar y presentación estática.
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
            profile=None,
            avatar_background_color=None,
            avatar_text_color=None,
            is_local=False,
        )


@dataclass(frozen=True, slots=True)
# ResolvedUserRecord conserva la referencia durable profile_key del usuario administrado.
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
        if profile_key == _GUEST_PROFILE_KEY:
            raise UsersDefinitionError('Resolved runtime user cannot use guest profile key')
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
                _user_profile_color(self.avatar_background_color),
            )
        if self.avatar_text_color is not None:
            object.__setattr__(
                self,
                'avatar_text_color',
                _user_profile_color(self.avatar_text_color),
            )

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


RuntimeUserRecord = PendingUserRecord | ResolvedUserRecord


def build_avatar_text(display_name: str) -> str:
    words = tuple(part for part in display_name.strip().split() if part)
    if not words:
        raise UsersDefinitionError('Display name must not be empty')
    if len(words) == 1:
        return words[0][:2].upper()
    return f'{words[0][0]}{words[-1][0]}'.upper()
