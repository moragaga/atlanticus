from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
# Define `NavigationProfileOption` como responsabilidad aislada dentro de Atlanticus.
class NavigationProfileOption:
    key: str
    label: str
    unrestricted: bool = False
    background_color: str | None = None
    text_color: str | None = None

    # Resuelve `post init` manteniendo validación y estado explícitos.
    def __post_init__(self) -> None:
        key = self.key.strip().casefold()
        label = self.label.strip()
        if not key or any(character.isspace() for character in key):
            raise ValueError('Navigation profile key is invalid')
        if not label:
            raise ValueError('Navigation profile label must not be empty')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'label', label)


_BASE_PROFILES = (
    NavigationProfileOption(key='local', label='Local', unrestricted=True),
    NavigationProfileOption(
        key='administrator',
        label='Administrador',
        unrestricted=True,
    ),
    NavigationProfileOption(key='guest', label='Guest'),
)


# Resuelve `resolve profile options` manteniendo validación y estado explícitos.
def resolve_profile_options(
    provider_options: tuple[NavigationProfileOption, ...] = (),
) -> tuple[NavigationProfileOption, ...]:
    merged = {profile.key: profile for profile in _BASE_PROFILES}
    order = [profile.key for profile in _BASE_PROFILES]
    for profile in provider_options:
        existing = merged.get(profile.key)
        unrestricted = existing.unrestricted if existing is not None else profile.unrestricted
        merged[profile.key] = replace(profile, unrestricted=unrestricted)
        if profile.key not in order:
            order.append(profile.key)
    return tuple(merged[key] for key in order)


# Resuelve `selectable profile options` manteniendo validación y estado explícitos.
def selectable_profile_options(
    provider_options: tuple[NavigationProfileOption, ...] = (),
) -> tuple[NavigationProfileOption, ...]:
    return tuple(
        profile for profile in resolve_profile_options(provider_options) if not profile.unrestricted
    )
