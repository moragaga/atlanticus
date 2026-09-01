# Implementa el History SharePoint de Navigation y relee el manifest justo antes del write.
# Si la revisión actual difiere de la esperada, rechaza la publicación sin modificar la historia.

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

from atlanticus.web.navigation.configuration.bundle import (
    NavigationConfigurationBundle,
    NavigationConfigurationSourceDocument,
    decode_navigation_configuration_source,
    encode_navigation_configuration_source,
)
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationPublisherError,
    NavigationConfigurationSourceError,
)


class SharePointFileGateway(Protocol):
    def read(self, *, filename: str, relative_path: str) -> str | None: ...

    def write(self, *, filename: str, relative_path: str, content: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SharePointNavigationConfigurationSettings:
    filename: str = 'navigation_configuration.json.gz'
    relative_path: str = 'navigation'

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError('SharePoint navigation filename must not be empty')
        if not self.relative_path.strip():
            raise ValueError('SharePoint navigation relative path must not be empty')


class SharePointNavigationConfigurationStore:
    def __init__(
        self,
        *,
        gateway: SharePointFileGateway,
        settings: SharePointNavigationConfigurationSettings,
    ) -> None:
        self._gateway = gateway
        self._settings = settings

    def fetch_bundle(self) -> NavigationConfigurationBundle | None:
        source = self._load_source()
        return source.current_bundle() if source is not None else None

    def publish_bundle(
        self,
        bundle: NavigationConfigurationBundle,
        *,
        expected_source_revision: str | None,
    ) -> None:
        try:
            current = self._load_source()
            current_bundle = current.current_bundle() if current is not None else None
            current_revision = current_bundle.revision if current_bundle is not None else None
            if current_revision != expected_source_revision:
                raise NavigationConfigurationSourceError(
                    'Navigation source revision changed before publication'
                )
            updated = (
                NavigationConfigurationSourceDocument.from_bundle(bundle)
                if current is None
                else current.publish(bundle)
            )
            if current == updated:
                return
            content = base64.b64encode(encode_navigation_configuration_source(updated)).decode(
                'ascii'
            )
            self._write_content(content)
        except NavigationConfigurationPublisherError, NavigationConfigurationSourceError:
            raise
        except Exception as error:
            raise NavigationConfigurationPublisherError(
                'Could not publish navigation configuration to SharePoint'
            ) from error

    def list_history(self, *, limit: int = 20) -> tuple[NavigationConfigurationBundle, ...]:
        source = self._load_source()
        return source.list_history(limit=limit) if source is not None else ()

    def fetch_revision(self, revision: str) -> NavigationConfigurationBundle | None:
        source = self._load_source()
        return source.fetch_revision(revision) if source is not None else None

    def _load_source(self) -> NavigationConfigurationSourceDocument | None:
        content = self._fetch_content()
        if content is None:
            return None
        try:
            payload = base64.b64decode(content, validate=True)
            return decode_navigation_configuration_source(payload)
        except Exception as error:
            raise NavigationConfigurationSourceError(
                'SharePoint navigation configuration content is invalid'
            ) from error

    def _fetch_content(self) -> str | None:
        try:
            return self._gateway.read(
                filename=self._settings.filename,
                relative_path=self._settings.relative_path,
            )
        except Exception as error:
            raise NavigationConfigurationSourceError(
                'Could not load navigation configuration from SharePoint'
            ) from error

    def _write_content(self, content: str) -> None:
        try:
            self._gateway.write(
                filename=self._settings.filename,
                relative_path=self._settings.relative_path,
                content=content,
            )
        except Exception as error:
            raise NavigationConfigurationPublisherError(
                'Could not publish navigation configuration to SharePoint'
            ) from error
