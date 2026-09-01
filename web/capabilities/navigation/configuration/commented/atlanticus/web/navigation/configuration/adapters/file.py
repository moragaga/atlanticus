# Implementa History local de Navigation y valida expected_source_revision inmediatamente antes de persistir.
# La comprobación final evita que una revisión nueva se absorba silenciosamente durante una publicación.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from atlanticus.web.navigation.configuration.bundle import (
    NavigationConfigurationBundle,
    NavigationConfigurationSourceDocument,
    decode_navigation_configuration_source,
    encode_navigation_configuration_source,
)
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationProjectionError,
    NavigationConfigurationPublisherError,
    NavigationConfigurationSourceError,
)
from atlanticus.web.navigation.configuration.projection import NavigationConfigurationProjection


@dataclass(frozen=True, slots=True)
class FileNavigationConfigurationSettings:
    root: Path
    filename: str = 'navigation_configuration.json.gz'


class FileNavigationConfigurationStore:
    def __init__(self, settings: FileNavigationConfigurationSettings) -> None:
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
            _atomic_write_bytes(self._path, encode_navigation_configuration_source(updated))
        except NavigationConfigurationSourceError:
            raise
        except Exception as error:
            raise NavigationConfigurationPublisherError(
                'Could not publish local navigation configuration'
            ) from error

    def list_history(self, *, limit: int = 20) -> tuple[NavigationConfigurationBundle, ...]:
        source = self._load_source()
        return source.list_history(limit=limit) if source is not None else ()

    def fetch_revision(self, revision: str) -> NavigationConfigurationBundle | None:
        source = self._load_source()
        return source.fetch_revision(revision) if source is not None else None

    def _load_source(self) -> NavigationConfigurationSourceDocument | None:
        if not self._path.exists():
            return None
        try:
            return decode_navigation_configuration_source(self._path.read_bytes())
        except Exception as error:
            raise NavigationConfigurationSourceError(
                'Local navigation configuration source is invalid'
            ) from error

    @property
    def _path(self) -> Path:
        return self._settings.root / self._settings.filename


@dataclass(frozen=True, slots=True)
class FileNavigationProjectionSettings:
    root: Path
    filename: str = 'navigation_projection.json'


class FileNavigationProjectionRepository:
    def __init__(self, settings: FileNavigationProjectionSettings) -> None:
        self._settings = settings

    def load(self) -> NavigationConfigurationProjection | None:
        if not self._path.exists():
            return None
        try:
            document = json.loads(self._path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            return NavigationConfigurationProjection.from_document(document)
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Local navigation projection is invalid'
            ) from error

    def save(
        self,
        projection: NavigationConfigurationProjection,
    ) -> NavigationConfigurationProjection:
        try:
            payload = json.dumps(
                projection.to_document(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path, payload)
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not write local navigation projection'
            ) from error
        return projection

    def health_check(self) -> bool:
        try:
            self._settings.root.mkdir(parents=True, exist_ok=True)
            return self._settings.root.is_dir()
        except OSError:
            return False

    @property
    def _path(self) -> Path:
        return self._settings.root / self._settings.filename


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
