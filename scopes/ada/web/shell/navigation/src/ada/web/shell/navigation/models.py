from __future__ import annotations

from dataclasses import dataclass

from atlanticus.web.errors import WebDefinitionError


@dataclass(frozen=True, slots=True)
class AdaNavigationAction:
    label: str
    href: str
    icon: str | None = None
    new_tab: bool = False

    def __post_init__(self) -> None:
        label = self.label.strip()
        href = self.href.strip()
        icon = self.icon.strip() if self.icon is not None else None
        if not label:
            raise WebDefinitionError('ADA navigation action label must not be empty')
        if not href:
            raise WebDefinitionError('ADA navigation action href must not be empty')
        if self.icon is not None and not icon:
            raise WebDefinitionError('ADA navigation action icon must not be empty when provided')
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'href', href)
        object.__setattr__(self, 'icon', icon)


@dataclass(frozen=True, slots=True)
class AdaNavigationView:
    title: str = 'ADA'
    subtitle: str | None = 'Navegación'
    action: AdaNavigationAction | None = None

    def __post_init__(self) -> None:
        title = self.title.strip()
        subtitle = self.subtitle.strip() if self.subtitle is not None else None
        if not title:
            raise WebDefinitionError('ADA navigation title must not be empty')
        object.__setattr__(self, 'title', title)
        object.__setattr__(self, 'subtitle', subtitle or None)
