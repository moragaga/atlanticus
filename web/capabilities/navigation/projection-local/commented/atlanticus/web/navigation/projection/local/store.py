# Espejo pedagógico del archivo productivo; conserva exactamente su comportamiento.
# Los comentarios en español describen responsabilidades sin alterar el contrato ejecutable.
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.projection_record import (
    navigation_projection_from_document,
    navigation_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
# Responsabilidad: LocalNavigationProjectionStoreSettings encapsula una frontera explícita del contrato vigente.
class LocalNavigationProjectionStoreSettings:
    root: Path


# Responsabilidad: LocalNavigationProjectionStore encapsula una frontera explícita del contrato vigente.
class LocalNavigationProjectionStore(ProjectionStore[NavigationConfigurationCatalog]):
    # Operación: __init__ mantiene la misma semántica que el código productivo.
    def __init__(self, settings: LocalNavigationProjectionStoreSettings) -> None:
        if not isinstance(settings, LocalNavigationProjectionStoreSettings):
            raise TypeError('settings must be LocalNavigationProjectionStoreSettings')
        self._settings = settings

    # Operación: get_active mantiene la misma semántica que el código productivo.
    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[NavigationConfigurationCatalog] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            projection = navigation_projection_from_document(document)
        except NavigationConfigurationProjectionError:
            raise
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Local navigation projection is invalid'
            ) from error
        if projection.source_key != source_key:
            raise NavigationConfigurationProjectionError(
                'Local navigation projection source key does not match request'
            )
        return projection

    # Operación: replace_active mantiene la misma semántica que el código productivo.
    def replace_active(
        self,
        projection: ProjectionRecord[NavigationConfigurationCatalog],
    ) -> ProjectionRecord[NavigationConfigurationCatalog]:
        try:
            payload = json.dumps(
                navigation_projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path(projection.source_key), payload)
        except NavigationConfigurationProjectionError:
            raise
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not write local navigation projection'
            ) from error
        return projection

    # Operación: _path mantiene la misma semántica que el código productivo.
    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'navigation_projection_{digest}.json'


# Operación: _atomic_write_bytes mantiene la misma semántica que el código productivo.
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
