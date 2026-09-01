# Espejo pedagógico del módulo productivo.
# Los comentarios explican responsabilidades sin alterar estructura ni comportamiento.
from __future__ import annotations

from dataclasses import dataclass

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.profiles import (
    ProfileDefinition,
    has_full_access,
    normalize_profile_color,
)


# Define EffectiveUser como frontera explícita del módulo y valida su contrato.
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
        background = self.avatar_background_color or self.profile.background_color
        text = self.avatar_text_color or self.profile.text_color
        object.__setattr__(
            self,
            'avatar_background_color',
            normalize_profile_color(background),
        )
        object.__setattr__(self, 'avatar_text_color', normalize_profile_color(text))

    @property
    def has_full_access(self) -> bool:
        return has_full_access(self.profile.key)


# Define ResolvedUserRecord como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class ResolvedUserRecord:
    user_id: str
    subject_id: str
    display_name: str
    email: str | None
    enabled: bool
    profile_key: str
    pending: bool = False
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None
    is_local: bool = False

    def __post_init__(self) -> None:
        profile_key = self.profile_key.strip().casefold()
        if not profile_key:
            raise UsersDefinitionError('Resolved user profile key must not be empty')
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

    def to_effective_user(self, *, profile: ProfileDefinition) -> EffectiveUser:
        if profile.key != self.profile_key:
            raise UsersDefinitionError('Resolved profile does not match user profile key')
        return EffectiveUser(
            user_id=self.user_id,
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=self.email,
            enabled=self.enabled,
            pending=self.pending,
            avatar_text=build_avatar_text(self.display_name),
            profile=profile,
            avatar_background_color=self.avatar_background_color,
            avatar_text_color=self.avatar_text_color,
            is_local=self.is_local,
        )


# Encapsula la operación build avatar text para mantener esta responsabilidad aislada.
def build_avatar_text(display_name: str) -> str:
    words = tuple(part for part in display_name.strip().split() if part)
    if not words:
        raise UsersDefinitionError('Display name must not be empty')
    if len(words) == 1:
        return words[0][:2].upper()
    return f'{words[0][0]}{words[-1][0]}'.upper()
