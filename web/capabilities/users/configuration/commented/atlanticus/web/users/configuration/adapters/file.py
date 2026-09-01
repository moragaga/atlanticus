# Implementa History local de Users y valida expected_source_revision inmediatamente antes de persistir.
# La semántica de concurrencia se mantiene igual a la de SharePoint aunque el almacenamiento sea file.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from atlanticus.web.users.configuration.bundle import (
    UsersConfigurationBundle,
    UsersConfigurationSourceDocument,
    decode_users_configuration_source,
    encode_users_configuration_source,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationProjectionError,
    UsersConfigurationPublisherError,
    UsersConfigurationSourceError,
)
from atlanticus.web.users.configuration.models import UsersConfigurationCatalog
from atlanticus.web.users.configuration.projection import UsersProjectionState
from atlanticus.web.users.profiles import ProfileCatalog, ProfileDefinition


@dataclass(frozen=True, slots=True)
class FileUsersConfigurationSettings:
    root: Path
    source_filename: str = 'users_configuration.json.gz'
    projection_filename: str = 'users_projection_state.json'


class FileUsersConfigurationStore:
    def __init__(self, settings: FileUsersConfigurationSettings) -> None:
        self._settings = settings

    def fetch_bundle(self) -> UsersConfigurationBundle | None:
        source = self._load_source()
        return source.current_bundle() if source is not None else None

    def publish_bundle(
        self,
        bundle: UsersConfigurationBundle,
        *,
        expected_source_revision: str | None,
    ) -> None:
        try:
            current = self._load_source()
            current_bundle = current.current_bundle() if current is not None else None
            current_revision = current_bundle.revision if current_bundle is not None else None
            if current_revision != expected_source_revision:
                raise UsersConfigurationSourceError(
                    'Users source revision changed before publication'
                )
            updated = (
                UsersConfigurationSourceDocument.from_bundle(bundle)
                if current is None
                else current.publish(bundle)
            )
            if current == updated:
                return
            _atomic_write_bytes(
                self._source_path,
                encode_users_configuration_source(updated),
            )
        except UsersConfigurationPublisherError, UsersConfigurationSourceError:
            raise
        except Exception as error:
            raise UsersConfigurationPublisherError(
                'Could not publish local users configuration'
            ) from error

    def list_history(self, *, limit: int = 20) -> tuple[UsersConfigurationBundle, ...]:
        source = self._load_source()
        return source.list_history(limit=limit) if source is not None else ()

    def fetch_revision(self, revision: str) -> UsersConfigurationBundle | None:
        source = self._load_source()
        return source.fetch_revision(revision) if source is not None else None

    def _load_source(self) -> UsersConfigurationSourceDocument | None:
        if not self._source_path.exists():
            return None
        try:
            return decode_users_configuration_source(self._source_path.read_bytes())
        except Exception as error:
            raise UsersConfigurationSourceError(
                'Local users configuration content is invalid'
            ) from error

    @property
    def _source_path(self) -> Path:
        return self._settings.root / self._settings.source_filename


class FileUsersProjectionRepository:
    def __init__(self, settings: FileUsersConfigurationSettings) -> None:
        self._settings = settings

    def load_state(self) -> UsersProjectionState | None:
        document = self._load_document()
        if document is None:
            return None
        try:
            return UsersProjectionState(
                revision=str(document['revision']),
                source_revision=str(document['source_revision']),
                projected_by=str(document['projected_by']),
                projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            )
        except Exception as error:
            raise UsersConfigurationProjectionError(
                'Could not read local users projection state'
            ) from error

    def load_catalog(self) -> UsersConfigurationCatalog | None:
        document = self._load_document()
        if document is None:
            return None
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return UsersConfigurationCatalog.from_document(catalog)
        except Exception as error:
            raise UsersConfigurationProjectionError(
                'Could not read local users projection catalog'
            ) from error

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState:
        state = UsersProjectionState.create(
            source_revision=bundle.revision,
            projected_by=actor,
        )
        document = {
            'revision': state.revision,
            'source_revision': state.source_revision,
            'projected_by': state.projected_by,
            'projected_at_utc': state.projected_at_utc.isoformat(),
            'catalog': bundle.catalog.to_document(),
        }
        try:
            _atomic_write_json(self._path, document)
        except Exception as error:
            raise UsersConfigurationProjectionError(
                'Could not write local users projection'
            ) from error
        return state

    def health_check(self) -> bool:
        try:
            self._settings.root.mkdir(parents=True, exist_ok=True)
            return os.access(self._settings.root, os.R_OK | os.W_OK)
        except OSError:
            return False

    def _load_document(self) -> dict[str, object] | None:
        if not self._path.exists():
            return None
        try:
            document = json.loads(self._path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            return document
        except Exception as error:
            raise UsersConfigurationProjectionError(
                'Could not read local users projection'
            ) from error

    @property
    def _path(self) -> Path:
        return self._settings.root / self._settings.projection_filename


class FileUsersProjectionProfileCatalog(ProfileCatalog):
    def __init__(self, repository: FileUsersProjectionRepository) -> None:
        if not isinstance(repository, FileUsersProjectionRepository):
            raise TypeError('repository must be FileUsersProjectionRepository')
        super().__init__()
        self._repository = repository

    @property
    def administrator_background_color(self) -> str:
        return self._current().administrator_background_color

    @property
    def administrator_text_color(self) -> str:
        return self._current().administrator_text_color

    @property
    def guest_background_color(self) -> str:
        return self._current().guest_background_color

    @property
    def guest_text_color(self) -> str:
        return self._current().guest_text_color

    @property
    def custom_profiles(self) -> tuple[ProfileDefinition, ...]:
        return self._current().custom_profiles

    def require(self, key: str) -> ProfileDefinition:
        return self._current().require(key)

    def all(self) -> tuple[ProfileDefinition, ...]:
        return self._current().all()

    def assignable(self) -> tuple[ProfileDefinition, ...]:
        return self._current().assignable()

    def restricted_access_profiles(self) -> tuple[ProfileDefinition, ...]:
        return self._current().restricted_access_profiles()

    def _current(self) -> ProfileCatalog:
        catalog = self._repository.load_catalog()
        if catalog is None:
            return ProfileCatalog()
        return catalog.profile_catalog()


def _atomic_write_json(path: Path, document: dict[str, object]) -> None:
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    _atomic_write_bytes(path, payload)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)
