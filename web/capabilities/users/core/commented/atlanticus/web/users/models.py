from __future__ import annotations

# Los modelos separan el usuario efectivo de un registro durable resuelto por la Source.
from dataclasses import dataclass

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.profiles import (
    GUEST_PROFILE_KEY,
    ProfileDefinition,
    normalize_profile_color,
)


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
        # Estas reglas impiden combinaciones ambiguas como Pending+Administrator o Pending+Disabled.
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


# ResolvedUserRecord sólo representa usuarios ya gestionados que provienen de UsersSource.
# Por eso no contiene un flag pending y tampoco admite el perfil Guest.
@dataclass(frozen=True, slots=True)
class ResolvedUserRecord:
    user_id: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    profile_key: str
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None
    is_local: bool = False

    def __post_init__(self) -> None:
        profile_key = self.profile_key.strip().casefold()
        if not profile_key:
            raise UsersDefinitionError('Resolved user profile key must not be empty')
        if profile_key == GUEST_PROFILE_KEY:
            raise UsersDefinitionError('Resolved source user cannot use guest profile')
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

    # Un registro durable siempre se convierte en un usuario efectivo no pendiente.
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


# El avatar se deriva de forma determinista del nombre visible.
def build_avatar_text(display_name: str) -> str:
    words = tuple(part for part in display_name.strip().split() if part)
    if not words:
        raise UsersDefinitionError('Display name must not be empty')
    if len(words) == 1:
        return words[0][:2].upper()
    return f'{words[0][0]}{words[-1][0]}'.upper()
