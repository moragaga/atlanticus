from __future__ import annotations

import re
from dataclasses import dataclass

from atlanticus.web.profiles.errors import ProfilesDefinitionError

_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def normalize_profile_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        raise ProfilesDefinitionError('Profile key must not be empty')
    if any(character.isspace() for character in normalized):
        raise ProfilesDefinitionError('Profile key must not contain spaces')
    return normalized


def normalize_profile_color(value: str) -> str:
    normalized = value.strip().upper()
    if not _HEX_COLOR.fullmatch(normalized):
        raise ProfilesDefinitionError('Profile color must use #RRGGBB format')
    return normalized


@dataclass(frozen=True, slots=True)
class ProfileDefinition:
    key: str
    label: str
    background_color: str
    text_color: str = '#FFFFFF'

    def __post_init__(self) -> None:
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
        catalog = {profile.key: profile for profile in SYSTEM_PROFILE_DEFINITIONS}
        for profile in profiles:
            if profile.key in SYSTEM_PROFILE_KEYS:
                raise ProfilesDefinitionError(f'System profile {profile.key!r} cannot be redefined')
            if profile.key in catalog:
                raise ProfilesDefinitionError(f'Duplicate profile key {profile.key!r}')
            catalog[profile.key] = profile
        self._profiles = catalog

    def require(self, key: str) -> ProfileDefinition:
        normalized = normalize_profile_key(key)
        try:
            return self._profiles[normalized]
        except KeyError as error:
            raise ProfilesDefinitionError(f'Unknown profile {normalized!r}') from error

    def all(self) -> tuple[ProfileDefinition, ...]:
        return tuple(self._profiles.values())
