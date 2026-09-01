from __future__ import annotations

import re
from dataclasses import dataclass

from atlanticus.web.users.errors import UsersDefinitionError

LOCAL_PROFILE_KEY = 'local'
ADMINISTRATOR_PROFILE_KEY = 'administrator'
GUEST_PROFILE_KEY = 'guest'
LOCAL_PROFILE_BACKGROUND_COLOR = '#3778C2'
LOCAL_PROFILE_TEXT_COLOR = '#FFFFFF'
LOCAL_JOHN_BACKGROUND_COLOR = '#3778C2'
LOCAL_JOHN_TEXT_COLOR = '#FFFFFF'
LOCAL_JANE_BACKGROUND_COLOR = '#C85D91'
LOCAL_JANE_TEXT_COLOR = '#FFFFFF'
DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR = '#673AB7'
DEFAULT_ADMINISTRATOR_TEXT_COLOR = '#FFFFFF'
DEFAULT_GUEST_BACKGROUND_COLOR = '#FF5722'
DEFAULT_GUEST_TEXT_COLOR = '#FFFFFF'
_SYSTEM_PROFILE_KEYS = frozenset(
    {
        LOCAL_PROFILE_KEY,
        ADMINISTRATOR_PROFILE_KEY,
        GUEST_PROFILE_KEY,
    }
)
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


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
            raise UsersDefinitionError('Profile label must not be empty')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'background_color', background_color)
        object.__setattr__(self, 'text_color', text_color)


class ProfileCatalog:
    def __init__(
        self,
        *,
        administrator_background_color: str = DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
        administrator_text_color: str = DEFAULT_ADMINISTRATOR_TEXT_COLOR,
        guest_background_color: str = DEFAULT_GUEST_BACKGROUND_COLOR,
        guest_text_color: str = DEFAULT_GUEST_TEXT_COLOR,
        custom_profiles: tuple[ProfileDefinition, ...] = (),
    ) -> None:
        system_profiles = (
            ProfileDefinition(
                key=LOCAL_PROFILE_KEY,
                label='Local',
                background_color=LOCAL_PROFILE_BACKGROUND_COLOR,
                text_color=LOCAL_PROFILE_TEXT_COLOR,
            ),
            ProfileDefinition(
                key=ADMINISTRATOR_PROFILE_KEY,
                label='Administrador',
                background_color=administrator_background_color,
                text_color=administrator_text_color,
            ),
            ProfileDefinition(
                key=GUEST_PROFILE_KEY,
                label='Invitado',
                background_color=guest_background_color,
                text_color=guest_text_color,
            ),
        )
        profiles = {profile.key: profile for profile in system_profiles}
        custom_keys: list[str] = []
        for profile in custom_profiles:
            if profile.key in _SYSTEM_PROFILE_KEYS:
                raise UsersDefinitionError(f'System profile {profile.key!r} cannot be redefined')
            if profile.key in profiles:
                raise UsersDefinitionError(f'Duplicate profile key {profile.key!r}')
            profiles[profile.key] = profile
            custom_keys.append(profile.key)
        self._profiles = profiles
        self._custom_keys = tuple(custom_keys)

    @property
    def administrator_background_color(self) -> str:
        return self._profiles[ADMINISTRATOR_PROFILE_KEY].background_color

    @property
    def administrator_text_color(self) -> str:
        return self._profiles[ADMINISTRATOR_PROFILE_KEY].text_color

    @property
    def guest_background_color(self) -> str:
        return self._profiles[GUEST_PROFILE_KEY].background_color

    @property
    def guest_text_color(self) -> str:
        return self._profiles[GUEST_PROFILE_KEY].text_color

    @property
    def custom_profiles(self) -> tuple[ProfileDefinition, ...]:
        return tuple(self._profiles[key] for key in self._custom_keys)

    def require(self, key: str) -> ProfileDefinition:
        normalized = normalize_profile_key(key)
        try:
            return self._profiles[normalized]
        except KeyError as error:
            raise UsersDefinitionError(f'Unknown profile {normalized!r}') from error

    def all(self) -> tuple[ProfileDefinition, ...]:
        return tuple(self._profiles.values())

    def assignable(self) -> tuple[ProfileDefinition, ...]:
        return (
            self._profiles[ADMINISTRATOR_PROFILE_KEY],
            *(self._profiles[key] for key in self._custom_keys),
        )

    def restricted_access_profiles(self) -> tuple[ProfileDefinition, ...]:
        return (
            self._profiles[GUEST_PROFILE_KEY],
            *(self._profiles[key] for key in self._custom_keys),
        )


def has_full_access(profile_key: str) -> bool:
    return normalize_profile_key(profile_key) in {
        LOCAL_PROFILE_KEY,
        ADMINISTRATOR_PROFILE_KEY,
    }


def profile_has_access(profile_key: str, allowed_profiles: tuple[str, ...]) -> bool:
    normalized_profile = normalize_profile_key(profile_key)
    if has_full_access(normalized_profile):
        return True
    return normalized_profile in {normalize_profile_key(value) for value in allowed_profiles}


def normalize_profile_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        raise UsersDefinitionError('Profile key must not be empty')
    if any(character.isspace() for character in normalized):
        raise UsersDefinitionError('Profile key must not contain spaces')
    return normalized


def normalize_profile_color(value: str) -> str:
    normalized = value.strip().upper()
    if not _HEX_COLOR.fullmatch(normalized):
        raise UsersDefinitionError('Profile color must use #RRGGBB format')
    return normalized
