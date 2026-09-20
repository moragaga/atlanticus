from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from ada.web.kpis.registry.models import KpiRegistry
from ada.web.kpis.registry.configuration.errors import KpiRegistryProjectionError
from ada.web.kpis.registry.configuration.projection_record import (
    kpi_registry_projection_from_document,
    kpi_registry_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class LocalKpiRegistryProjectionStoreSettings:
    root: Path


class LocalKpiRegistryProjectionStore(ProjectionStore[KpiRegistry]):
    def __init__(self, settings: LocalKpiRegistryProjectionStoreSettings) -> None:
        if not isinstance(settings, LocalKpiRegistryProjectionStoreSettings):
            raise TypeError('settings must be LocalKpiRegistryProjectionStoreSettings')
        self._settings = settings

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[KpiRegistry] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            projection = kpi_registry_projection_from_document(document)
        except KpiRegistryProjectionError:
            raise
        except Exception as error:
            raise KpiRegistryProjectionError('Local KPI Registry projection is invalid') from error
        if projection.source_key != source_key:
            raise KpiRegistryProjectionError(
                'Local KPI Registry projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[KpiRegistry],
    ) -> ProjectionRecord[KpiRegistry]:
        try:
            payload = json.dumps(
                kpi_registry_projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path(projection.source_key), payload)
        except KpiRegistryProjectionError:
            raise
        except Exception as error:
            raise KpiRegistryProjectionError(
                'Could not write local KPI Registry projection'
            ) from error
        return projection

    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'kpi_registry_projection_{digest}.json'


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
