from __future__ import annotations

import re
from dataclasses import dataclass

from ada.web.access.errors import AdaAccessDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog, normalize_profile_key

_ACCESS_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')


def normalize_access_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not _ACCESS_KEY_PATTERN.fullmatch(normalized):
        raise AdaAccessDefinitionError('ADA access key has an invalid format')
    return normalized


def _normalize_unique_access_keys(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(normalize_access_key(value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise AdaAccessDefinitionError('ADA access keys must be unique')
    return normalized


# Un grant pertenece a un perfil de Profiles y contiene únicamente permisos application-specific de ADA.
@dataclass(frozen=True, slots=True)
class ProfileAccessGrant:
    profile_key: str
    access_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'profile_key', normalize_profile_key(self.profile_key))
        object.__setattr__(
            self,
            'access_keys',
            _normalize_unique_access_keys(tuple(self.access_keys)),
        )


# El resultado efectivo ya no posee ni decide qué perfil tiene un usuario; recibe una profile_key.
@dataclass(frozen=True, slots=True)
class EffectiveAdaAccess:
    profile_key: str
    access_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'profile_key', normalize_profile_key(self.profile_key))
        object.__setattr__(
            self,
            'access_keys',
            _normalize_unique_access_keys(tuple(self.access_keys)),
        )


# Access sólo verifica que sus grants referencien perfiles existentes.
def validate_profile_references(
    *,
    profile_keys: tuple[str, ...],
    profiles: ProfileCatalog,
) -> None:
    for profile_key in profile_keys:
        profiles.require(profile_key)
