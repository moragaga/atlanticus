from __future__ import annotations

import re
from dataclasses import dataclass

from atlanticus.web.profiles.errors import ProfilesDefinitionError

# Este patrón valida el contrato visual común de todos los perfiles.
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def normalize_profile_key(value: str) -> str:
    # Las claves son case-insensitive, se almacenan en casefold y no permiten espacios internos.
    normalized = value.strip().casefold()
    if not normalized:
        raise ProfilesDefinitionError('Profile key must not be empty')
    if any(character.isspace() for character in normalized):
        raise ProfilesDefinitionError('Profile key must not contain spaces')
    return normalized


def normalize_profile_color(value: str) -> str:
    # Los colores se normalizan a mayúsculas para mantener una representación canónica.
    normalized = value.strip().upper()
    if not _HEX_COLOR.fullmatch(normalized):
        raise ProfilesDefinitionError('Profile color must use #RRGGBB format')
    return normalized


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    # Un perfil se define por una identidad lógica y una representación visual estable.
    key: str
    label: str
    background_color: str
    text_color: str = '#FFFFFF'

    def __post_init__(self) -> None:
        # La definición se normaliza una sola vez para que todos los consumers
        # usen valores canónicos.
        key = normalize_profile_key(self.key)
        label = self.label.strip()
        background_color = normalize_profile_color(self.background_color)
        text_color = normalize_profile_color(self.text_color)
        if not label:
            raise ProfilesDefinitionError('Profile label must not be empty')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'background_color', background_color)
        object.__setattr__(self, 'text_color', text_color)


# Estos cuatro perfiles pertenecen al sistema y existen aunque no haya configuración publicada.
# Sus atributos visuales son code-defined: cambiarlos requiere un despliegue y
# no una mutación Source.
BASIC_PROFILE_KEY = 'basic'
ROOT_PROFILE_KEY = 'root'
GUEST_PROFILE_KEY = 'guest'
LOCAL_PROFILE_KEY = 'local'

BASIC_PROFILE = ProfileDefinition(
    key=BASIC_PROFILE_KEY,
    label='Basic',
    background_color='#EC407A',
)
ROOT_PROFILE = ProfileDefinition(
    key=ROOT_PROFILE_KEY,
    label='Root',
    background_color='#673AB7',
)
GUEST_PROFILE = ProfileDefinition(
    key=GUEST_PROFILE_KEY,
    label='Guest',
    background_color='#FF5722',
)
LOCAL_PROFILE = ProfileDefinition(
    key=LOCAL_PROFILE_KEY,
    label='Local',
    background_color='#3778C2',
)
SYSTEM_PROFILE_DEFINITIONS = (
    BASIC_PROFILE,
    ROOT_PROFILE,
    GUEST_PROFILE,
    LOCAL_PROFILE,
)
SYSTEM_PROFILE_KEYS = frozenset(profile.key for profile in SYSTEM_PROFILE_DEFINITIONS)


class ProfileCatalog:
    def __init__(
        self,
        *,
        profiles: tuple[ProfileDefinition, ...] = (),
    ) -> None:
        # El catálogo efectivo comienza siempre con los perfiles de sistema.
        catalog = {profile.key: profile for profile in SYSTEM_PROFILE_DEFINITIONS}
        for profile in profiles:
            # Los perfiles configurables pueden agregar nuevas keys, pero nunca
            # redefinir las del sistema.
            if profile.key in SYSTEM_PROFILE_KEYS:
                raise ProfilesDefinitionError(f'System profile {profile.key!r} cannot be redefined')
            if profile.key in catalog:
                raise ProfilesDefinitionError(f'Duplicate profile key {profile.key!r}')
            catalog[profile.key] = profile
        # dict conserva el orden: system profiles primero y configurados después.
        self._profiles = catalog

    def require(self, key: str) -> ProfileDefinition:
        # Todos los consumers resuelven system y configured profiles mediante el mismo contrato.
        normalized = normalize_profile_key(key)
        try:
            return self._profiles[normalized]
        except KeyError as error:
            raise ProfilesDefinitionError(f'Unknown profile {normalized!r}') from error

    def all(self) -> tuple[ProfileDefinition, ...]:
        # La vista efectiva incluye siempre system profiles más los configurados recibidos.
        return tuple(self._profiles.values())
