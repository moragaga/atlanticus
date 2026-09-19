from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.configuration.projection_record import (
    profiles_projection_from_document,
    profiles_projection_to_document,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class LocalProfilesProjectionStoreSettings:
    root: Path


class LocalProfilesProjectionStore(ProjectionStore[ProfileCatalog]):
    def __init__(self, settings: LocalProfilesProjectionStoreSettings) -> None:
        if not isinstance(settings, LocalProfilesProjectionStoreSettings):
            raise TypeError('settings must be LocalProfilesProjectionStoreSettings')
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[ProfileCatalog] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            projection = profiles_projection_from_document(document)
        except ProfilesConfigurationProjectionError:
            raise
        except Exception as error:
            raise ProfilesConfigurationProjectionError(
                'Local profiles projection is invalid'
            ) from error
        if projection.source_key != source_key:
            raise ProfilesConfigurationProjectionError(
                'Local profiles projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[ProfileCatalog],
    ) -> ProjectionRecord[ProfileCatalog]:
        try:
            payload = json.dumps(
                profiles_projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path(projection.source_key), payload)
        except ProfilesConfigurationProjectionError:
            raise
        except Exception as error:
            raise ProfilesConfigurationProjectionError(
                'Could not write local profiles projection'
            ) from error
        return projection

    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'profiles_projection_{digest}.json'


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
