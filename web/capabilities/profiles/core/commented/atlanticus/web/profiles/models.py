from __future__ import annotations

import re
from dataclasses import dataclass

from atlanticus.web.profiles.errors import ProfilesDefinitionError

# Este patrón valida el contrato visual común de los perfiles sin conocer ningún consumidor.
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    # Un perfil funcional se define únicamente por identidad lógica y atributos visuales.
    key: str
    label: str
    background_color: str
    text_color: str = '#FFFFFF'

    def __post_init__(self) -> None:
        # La definición se normaliza al construirse para que el resto del dominio trabaje con valores canónicos.
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


class ProfileCatalog:
    def __init__(
        self,
        *,
        profiles: tuple[ProfileDefinition, ...] = (),
    ) -> None:
        # El catálogo no fabrica perfiles del sistema: contiene exactamente los perfiles funcionales recibidos.
        catalog: dict[str, ProfileDefinition] = {}
        for profile in profiles:
            # Las claves ya vienen normalizadas por ProfileDefinition, por lo que una colisión es una duplicidad real.
            if profile.key in catalog:
                raise ProfilesDefinitionError(f'Duplicate profile key {profile.key!r}')
            catalog[profile.key] = profile
        # dict conserva el orden de inserción y permite lookup directo por clave canónica.
        self._profiles = catalog

    def require(self, key: str) -> ProfileDefinition:
        # El consumidor puede usar una variante normalizable de la clave y recibe siempre la definición canónica.
        normalized = normalize_profile_key(key)
        try:
            return self._profiles[normalized]
        except KeyError as error:
            raise ProfilesDefinitionError(f'Unknown profile {normalized!r}') from error

    def all(self) -> tuple[ProfileDefinition, ...]:
        # Se expone una vista inmutable y ordenada de todos los perfiles del catálogo.
        return tuple(self._profiles.values())


def normalize_profile_key(value: str) -> str:
    # Las claves son case-insensitive, se almacenan en casefold y no permiten espacios internos.
    normalized = value.strip().casefold()
    if not normalized:
        raise ProfilesDefinitionError('Profile key must not be empty')
    if any(character.isspace() for character in normalized):
        raise ProfilesDefinitionError('Profile key must not contain spaces')
    return normalized


def normalize_profile_color(value: str) -> str:
    # Los colores se normalizan a mayúsculas para evitar representaciones equivalentes distintas.
    normalized = value.strip().upper()
    if not _HEX_COLOR.fullmatch(normalized):
        raise ProfilesDefinitionError('Profile color must use #RRGGBB format')
    return normalized
