# Contratos visuales inyectables de Navigation; no contienen configuración de negocio.
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
    # La composition root inyecta assets institucionales y versión; Navigation sólo los presenta.
    title: str = 'Asistente de Decisiones Ágiles'
    subtitle: str | None = None
    brand_logo_src: str | None = None
    brand_logo_alt: str = 'ADA'
    footer_logo_src: str | None = None
    footer_logo_alt: str = 'Minera Los Pelambres'
    application_version: str | None = None
    action: AdaNavigationAction | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'title', _text(self.title, 'title'))
        object.__setattr__(self, 'subtitle', _optional_text(self.subtitle, 'subtitle'))
        object.__setattr__(
            self,
            'brand_logo_src',
            _optional_text(self.brand_logo_src, 'brand logo source'),
        )
        object.__setattr__(self, 'brand_logo_alt', _text(self.brand_logo_alt, 'brand logo alt'))
        object.__setattr__(
            self,
            'footer_logo_src',
            _optional_text(self.footer_logo_src, 'footer logo source'),
        )
        object.__setattr__(
            self,
            'footer_logo_alt',
            _text(self.footer_logo_alt, 'footer logo alt'),
        )
        object.__setattr__(
            self,
            'application_version',
            _optional_text(self.application_version, 'application version'),
        )


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebDefinitionError(f'ADA navigation {field_name} must not be empty')
    return value.strip()


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)
