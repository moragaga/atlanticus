from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from atlanticus.web.errors import WebDefinitionError

_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


@dataclass(frozen=True, slots=True)
class NavigationUser:
    display_name: str
    profile_key: str
    profile_label: str
    profile_background_color: str
    profile_text_color: str
    avatar_text: str
    avatar_background_color: str | None = None
    avatar_text_color: str | None = None
    email: str | None = None
    avatar_src: str | None = None

    def __post_init__(self) -> None:
        display_name = self.display_name.strip()
        profile_key = _normalize_profile_key(self.profile_key)
        profile_label = self.profile_label.strip()
        profile_background_color = self.profile_background_color.strip().upper()
        profile_text_color = self.profile_text_color.strip().upper()
        avatar_background_color = (
            (self.avatar_background_color or profile_background_color).strip().upper()
        )
        avatar_text_color = (self.avatar_text_color or profile_text_color).strip().upper()
        avatar_text = self.avatar_text.strip()
        if not display_name:
            raise WebDefinitionError('Navigation user display name must not be empty')
        if not profile_label:
            raise WebDefinitionError('Navigation user profile label must not be empty')
        if not _HEX_COLOR.fullmatch(profile_background_color):
            raise WebDefinitionError(
                'Navigation user profile background color must use #RRGGBB format'
            )
        if not _HEX_COLOR.fullmatch(profile_text_color):
            raise WebDefinitionError('Navigation user profile text color must use #RRGGBB format')
        if not _HEX_COLOR.fullmatch(avatar_background_color):
            raise WebDefinitionError(
                'Navigation user avatar background color must use #RRGGBB format'
            )
        if not _HEX_COLOR.fullmatch(avatar_text_color):
            raise WebDefinitionError('Navigation user avatar text color must use #RRGGBB format')
        if not avatar_text or len(avatar_text) > 4:
            raise WebDefinitionError(
                'Navigation user avatar text must contain between 1 and 4 characters'
            )
        if self.email is not None and not self.email.strip():
            raise WebDefinitionError('Navigation user email must not be empty when provided')
        if self.avatar_src is not None and not self.avatar_src.strip():
            raise WebDefinitionError(
                'Navigation user avatar source must not be empty when provided'
            )
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'profile_key', profile_key)
        object.__setattr__(self, 'profile_label', profile_label)
        object.__setattr__(self, 'profile_background_color', profile_background_color)
        object.__setattr__(self, 'profile_text_color', profile_text_color)
        object.__setattr__(self, 'avatar_background_color', avatar_background_color)
        object.__setattr__(self, 'avatar_text_color', avatar_text_color)
        object.__setattr__(self, 'avatar_text', avatar_text)


@dataclass(frozen=True, slots=True)
class NavigationPrincipal:
    access_key: str
    user: NavigationUser
    unrestricted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, 'access_key', _normalize_profile_key(self.access_key))


@dataclass(frozen=True, slots=True)
class NavigationLinkDefinition:
    key: str
    label: str
    href: str
    order: int = 0
    icon: str | None = None
    enabled: bool = True
    new_tab: bool = False
    force_reload: bool = False
    allowed_profiles: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _validate_key(self.key, label='Navigation link key')
        if not self.label.strip():
            raise WebDefinitionError('Navigation link label must not be empty')
        _validate_href(self.href)
        if self.icon is not None and not self.icon.strip():
            raise WebDefinitionError('Navigation link icon must not be empty when provided')
        if self.allowed_profiles is not None:
            object.__setattr__(
                self,
                'allowed_profiles',
                _normalize_allowed_profiles(self.allowed_profiles),
            )

    @property
    def is_external(self) -> bool:
        return not self.href.startswith('/')

    def effective_profiles(self, parent: NavigationGroupDefinition | None) -> tuple[str, ...]:
        if self.allowed_profiles is not None:
            return self.allowed_profiles
        if parent is not None:
            return parent.allowed_profiles
        return ()

    def to_resolved(self) -> NavigationLink:
        return NavigationLink(
            key=self.key,
            label=self.label,
            href=self.href,
            order=self.order,
            icon=self.icon,
            enabled=self.enabled,
            new_tab=self.new_tab,
            force_reload=self.force_reload,
        )


@dataclass(frozen=True, slots=True)
class NavigationGroupDefinition:
    key: str
    label: str
    links: tuple[NavigationLinkDefinition, ...]
    order: int = 0
    icon: str | None = None
    enabled: bool = True
    expanded: bool = False
    allowed_profiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_key(self.key, label='Navigation group key')
        if not self.label.strip():
            raise WebDefinitionError('Navigation group label must not be empty')
        if self.icon is not None and not self.icon.strip():
            raise WebDefinitionError('Navigation group icon must not be empty when provided')
        object.__setattr__(
            self,
            'allowed_profiles',
            _normalize_allowed_profiles(self.allowed_profiles),
        )
        link_keys = [link.key for link in self.links]
        if len(link_keys) != len(set(link_keys)):
            raise WebDefinitionError(f'Navigation group contains duplicated link keys: {self.key}')

    def to_resolved(self, *, links: tuple[NavigationLink, ...]) -> NavigationGroup:
        return NavigationGroup(
            key=self.key,
            label=self.label,
            links=links,
            order=self.order,
            icon=self.icon,
            enabled=self.enabled,
            expanded=self.expanded,
        )


@dataclass(frozen=True, slots=True)
class NavigationDefinition:
    links: tuple[NavigationLinkDefinition, ...] = ()
    groups: tuple[NavigationGroupDefinition, ...] = ()
    home_route_key: str | None = None

    def __post_init__(self) -> None:
        group_keys = [group.key for group in self.groups]
        if len(group_keys) != len(set(group_keys)):
            raise WebDefinitionError('Navigation definition contains duplicated group keys')
        link_keys = [link.key for link in self.links]
        link_keys.extend(link.key for group in self.groups for link in group.links)
        if len(link_keys) != len(set(link_keys)):
            raise WebDefinitionError('Navigation definition contains duplicated link keys')
        if self.home_route_key is not None:
            home_route_key = self.home_route_key.strip()
            _validate_key(home_route_key, label='Navigation home route key')
            home = self.find_link(home_route_key)
            if home is None:
                raise WebDefinitionError('Navigation home route key must reference a link')
            if home.is_external:
                raise WebDefinitionError('Navigation home route must reference an internal link')
            object.__setattr__(self, 'home_route_key', home_route_key)

    def find_link(self, key: str) -> NavigationLinkDefinition | None:
        normalized = key.strip()
        for link in self.links:
            if link.key == normalized:
                return link
        for group in self.groups:
            for link in group.links:
                if link.key == normalized:
                    return link
        return None

    def configured_profiles(self) -> tuple[str, ...]:
        profiles: list[str] = []
        seen: set[str] = set()
        for key in _iter_allowed_profiles(self):
            if key in seen:
                continue
            seen.add(key)
            profiles.append(key)
        return tuple(profiles)


@dataclass(frozen=True, slots=True)
class NavigationLink:
    key: str
    label: str
    href: str
    order: int = 0
    icon: str | None = None
    enabled: bool = True
    new_tab: bool = False
    force_reload: bool = False

    def __post_init__(self) -> None:
        _validate_key(self.key, label='Navigation link key')
        if not self.label.strip():
            raise WebDefinitionError('Navigation link label must not be empty')
        _validate_href(self.href)
        if self.icon is not None and not self.icon.strip():
            raise WebDefinitionError('Navigation link icon must not be empty when provided')

    @property
    def is_external(self) -> bool:
        return not self.href.startswith('/')


@dataclass(frozen=True, slots=True)
class NavigationGroup:
    key: str
    label: str
    links: tuple[NavigationLink, ...]
    order: int = 0
    icon: str | None = None
    enabled: bool = True
    expanded: bool = False

    def __post_init__(self) -> None:
        _validate_key(self.key, label='Navigation group key')
        if not self.label.strip():
            raise WebDefinitionError('Navigation group label must not be empty')
        if not self.links:
            raise WebDefinitionError('Navigation group must contain at least one link')
        if self.icon is not None and not self.icon.strip():
            raise WebDefinitionError('Navigation group icon must not be empty when provided')
        link_keys = [link.key for link in self.links]
        if len(link_keys) != len(set(link_keys)):
            raise WebDefinitionError(f'Navigation group contains duplicated link keys: {self.key}')


@dataclass(frozen=True, slots=True)
class NavigationMenu:
    user: NavigationUser
    links: tuple[NavigationLink, ...] = ()
    groups: tuple[NavigationGroup, ...] = ()

    def __post_init__(self) -> None:
        group_keys = [group.key for group in self.groups]
        if len(group_keys) != len(set(group_keys)):
            raise WebDefinitionError('Navigation menu contains duplicated group keys')
        link_keys = [link.key for link in self.links]
        link_keys.extend(link.key for group in self.groups for link in group.links)
        if len(link_keys) != len(set(link_keys)):
            raise WebDefinitionError('Navigation menu contains duplicated link keys')


def _iter_allowed_profiles(definition: NavigationDefinition):
    for link in definition.links:
        if link.allowed_profiles is not None:
            yield from link.allowed_profiles
    for group in definition.groups:
        yield from group.allowed_profiles
        for link in group.links:
            if link.allowed_profiles is not None:
                yield from link.allowed_profiles


def _normalize_allowed_profiles(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalize_profile_key(value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return tuple(normalized)


def _normalize_profile_key(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized:
        raise WebDefinitionError('Navigation profile key must not be empty')
    if any(character.isspace() for character in normalized):
        raise WebDefinitionError('Navigation profile key must not contain spaces')
    return normalized


def _validate_key(value: str, *, label: str) -> None:
    if not _KEY_PATTERN.fullmatch(value):
        raise WebDefinitionError(f'{label} has an invalid format')


def _validate_href(value: str) -> None:
    if value.startswith('/') and not value.startswith('//'):
        return
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise WebDefinitionError('Navigation link href must be an absolute path or HTTP(S) URL')
