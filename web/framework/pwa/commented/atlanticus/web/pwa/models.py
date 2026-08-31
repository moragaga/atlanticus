# Espejo comentado: contrato tipado de metadata PWA independiente de una Tool.
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.models import ApplicationMetadata

_HEX_COLOR_PATTERN = re.compile(r'^#[0-9a-fA-F]{6}$')
_ICON_SIZES_PATTERN = re.compile(r'^(any|\d+x\d+)(\s+(any|\d+x\d+))*$')
_VALID_ICON_PURPOSES = frozenset({'any', 'maskable', 'monochrome'})


class WebPwaDisplay(StrEnum):
    STANDALONE = 'standalone'
    FULLSCREEN = 'fullscreen'
    MINIMAL_UI = 'minimal-ui'
    BROWSER = 'browser'


@dataclass(frozen=True, slots=True)
class WebPwaIcon:
    src: str
    sizes: str
    mime_type: str = 'image/png'
    purpose: tuple[str, ...] = ('any',)

    def __post_init__(self) -> None:
        if not self.src.startswith('/'):
            raise WebDefinitionError('PWA icon src must be an absolute application path')
        if not _ICON_SIZES_PATTERN.fullmatch(self.sizes.strip()):
            raise WebDefinitionError('PWA icon sizes have an invalid format')
        normalized_purpose = tuple(
            dict.fromkeys(item.strip() for item in self.purpose if item.strip())
        )
        if not normalized_purpose or any(
            item not in _VALID_ICON_PURPOSES for item in normalized_purpose
        ):
            raise WebDefinitionError('PWA icon purpose has an invalid value')
        if not self.mime_type.strip():
            raise WebDefinitionError('PWA icon mime type must not be empty')
        object.__setattr__(self, 'purpose', normalized_purpose)

    def to_manifest(self) -> dict[str, str]:
        return {
            'src': self.src,
            'sizes': self.sizes.strip(),
            'type': self.mime_type.strip(),
            'purpose': ' '.join(self.purpose),
        }


@dataclass(frozen=True, slots=True)
class WebPwaDefinition:
    application_id: str
    version: str
    name: str
    short_name: str
    theme_color: str
    background_color: str
    start_url: str = '/'
    scope: str = '/'
    display: WebPwaDisplay = WebPwaDisplay.STANDALONE
    icons: tuple[WebPwaIcon, ...] = ()

    def __post_init__(self) -> None:
        if not self.application_id.strip():
            raise WebDefinitionError('PWA application id must not be empty')
        if not self.version.strip():
            raise WebDefinitionError('PWA version must not be empty')
        if not self.name.strip():
            raise WebDefinitionError('PWA name must not be empty')
        if not self.short_name.strip():
            raise WebDefinitionError('PWA short name must not be empty')
        if not self.start_url.startswith('/'):
            raise WebDefinitionError('PWA start URL must be an absolute application path')
        if not self.scope.startswith('/'):
            raise WebDefinitionError('PWA scope must be an absolute application path')
        if not isinstance(self.display, WebPwaDisplay):
            raise WebDefinitionError('PWA display must be a WebPwaDisplay value')
        if not _HEX_COLOR_PATTERN.fullmatch(self.theme_color):
            raise WebDefinitionError('PWA theme color must use #RRGGBB format')
        if not _HEX_COLOR_PATTERN.fullmatch(self.background_color):
            raise WebDefinitionError('PWA background color must use #RRGGBB format')

    @classmethod
    def from_application(
        cls,
        metadata: ApplicationMetadata,
        *,
        short_name: str,
        theme_color: str,
        background_color: str,
        icons: tuple[WebPwaIcon, ...] = (),
        start_url: str = '/',
        scope: str = '/',
        display: WebPwaDisplay = WebPwaDisplay.STANDALONE,
    ) -> WebPwaDefinition:
        return cls(
            application_id=metadata.application_id,
            version=metadata.version,
            name=metadata.display_name,
            short_name=short_name,
            theme_color=theme_color,
            background_color=background_color,
            start_url=start_url,
            scope=scope,
            display=display,
            icons=icons,
        )

    def to_manifest(self) -> dict[str, object]:
        manifest: dict[str, object] = {
            'id': self.application_id,
            'name': self.name,
            'short_name': self.short_name,
            'start_url': self.start_url,
            'scope': self.scope,
            'display': self.display.value,
            'theme_color': self.theme_color,
            'background_color': self.background_color,
        }
        if self.icons:
            manifest['icons'] = [icon.to_manifest() for icon in self.icons]
        return manifest
