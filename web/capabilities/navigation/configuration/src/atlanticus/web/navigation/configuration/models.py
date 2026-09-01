from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationGroupDefinition,
    NavigationLinkDefinition,
)
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationValidationError


def _required(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise NavigationConfigurationValidationError(f'{label} must not be empty')
    return normalized


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class NavigationLinkConfiguration:
    key: str
    label: str
    href: str
    order: int = 0
    icon: str | None = None
    enabled: bool = True
    new_tab: bool = False
    force_reload: bool = False
    allowed_profiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        definition = self.to_definition()
        object.__setattr__(self, 'key', definition.key)
        object.__setattr__(self, 'label', _required(self.label, label='Navigation link label'))
        object.__setattr__(self, 'href', _required(self.href, label='Navigation link href'))
        object.__setattr__(self, 'icon', _optional(self.icon))
        object.__setattr__(self, 'allowed_profiles', definition.allowed_profiles or ())

    def to_definition(self) -> NavigationLinkDefinition:
        try:
            return NavigationLinkDefinition(
                key=self.key.strip(),
                label=self.label.strip(),
                href=self.href.strip(),
                order=self.order,
                icon=_optional(self.icon),
                enabled=self.enabled,
                new_tab=self.new_tab,
                force_reload=self.force_reload,
                allowed_profiles=self.allowed_profiles,
            )
        except WebDefinitionError as error:
            raise NavigationConfigurationValidationError(str(error)) from error

    def to_document(self) -> dict[str, object]:
        return {
            'key': self.key,
            'label': self.label,
            'href': self.href,
            'order': self.order,
            'icon': self.icon,
            'enabled': self.enabled,
            'new_tab': self.new_tab,
            'force_reload': self.force_reload,
            'allowed_profiles': list(self.allowed_profiles),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> NavigationLinkConfiguration:
        try:
            raw_profiles = document.get('allowed_profiles', [])
            if not isinstance(raw_profiles, list):
                raise TypeError
            return cls(
                key=str(document['key']),
                label=str(document['label']),
                href=str(document['href']),
                order=int(document.get('order', 0)),
                icon=(str(document['icon']) if document.get('icon') is not None else None),
                enabled=_require_bool(document.get('enabled', True)),
                new_tab=_require_bool(document.get('new_tab', False)),
                force_reload=_require_bool(document.get('force_reload', False)),
                allowed_profiles=tuple(str(item) for item in raw_profiles),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation link configuration contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class NavigationGroupConfiguration:
    key: str
    label: str
    links: tuple[NavigationLinkConfiguration, ...] = ()
    order: int = 0
    icon: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        definition = self.to_definition()
        object.__setattr__(self, 'key', definition.key)
        object.__setattr__(self, 'label', _required(self.label, label='Navigation group label'))
        object.__setattr__(self, 'icon', _optional(self.icon))

    def to_definition(self) -> NavigationGroupDefinition:
        try:
            return NavigationGroupDefinition(
                key=self.key.strip(),
                label=self.label.strip(),
                links=tuple(link.to_definition() for link in self.links),
                order=self.order,
                icon=_optional(self.icon),
                enabled=self.enabled,
                expanded=False,
                allowed_profiles=(),
            )
        except WebDefinitionError as error:
            raise NavigationConfigurationValidationError(str(error)) from error

    def to_document(self) -> dict[str, object]:
        return {
            'key': self.key,
            'label': self.label,
            'links': [link.to_document() for link in self.links],
            'order': self.order,
            'icon': self.icon,
            'enabled': self.enabled,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> NavigationGroupConfiguration:
        try:
            raw_links = document.get('links', [])
            if not isinstance(raw_links, list):
                raise TypeError
            return cls(
                key=str(document['key']),
                label=str(document['label']),
                links=tuple(
                    NavigationLinkConfiguration.from_document(dict(item)) for item in raw_links
                ),
                order=int(document.get('order', 0)),
                icon=(str(document['icon']) if document.get('icon') is not None else None),
                enabled=_require_bool(document.get('enabled', True)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation group configuration contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class NavigationConfigurationCatalog:
    links: tuple[NavigationLinkConfiguration, ...] = ()
    groups: tuple[NavigationGroupConfiguration, ...] = ()

    def __post_init__(self) -> None:
        self.to_definition()

    def to_definition(self) -> NavigationDefinition:
        try:
            return NavigationDefinition(
                links=tuple(link.to_definition() for link in self.links),
                groups=tuple(group.to_definition() for group in self.groups),
            )
        except WebDefinitionError as error:
            raise NavigationConfigurationValidationError(str(error)) from error

    def configured_profiles(self) -> tuple[str, ...]:
        return self.to_definition().configured_profiles()

    def to_document(self) -> dict[str, object]:
        return {
            'links': [link.to_document() for link in self.links],
            'groups': [group.to_document() for group in self.groups],
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> NavigationConfigurationCatalog:
        try:
            raw_links = document.get('links', [])
            raw_groups = document.get('groups', [])
            if not isinstance(raw_links, list) or not isinstance(raw_groups, list):
                raise TypeError
            return cls(
                links=tuple(
                    NavigationLinkConfiguration.from_document(dict(item)) for item in raw_links
                ),
                groups=tuple(
                    NavigationGroupConfiguration.from_document(dict(item)) for item in raw_groups
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation configuration catalog contract is invalid'
            ) from error


def _require_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError
    return value
