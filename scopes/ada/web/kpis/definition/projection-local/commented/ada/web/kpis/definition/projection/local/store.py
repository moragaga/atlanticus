# Persistencia local atómica de la proyección Definition.
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.configuration.errors import KpiDefinitionProjectionError
from ada.web.kpis.definition.configuration.projection_record import (
    kpi_definition_projection_from_document,
    kpi_definition_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class LocalKpiDefinitionProjectionStoreSettings:
    root: Path


class LocalKpiDefinitionProjectionStore(ProjectionStore[KpiDefinitionCatalog]):
    def __init__(self, settings: LocalKpiDefinitionProjectionStoreSettings) -> None:
        if not isinstance(settings, LocalKpiDefinitionProjectionStoreSettings):
            raise TypeError('settings must be LocalKpiDefinitionProjectionStoreSettings')
        self._settings = settings

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[KpiDefinitionCatalog] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            projection = kpi_definition_projection_from_document(document)
        except KpiDefinitionProjectionError:
            raise
        except Exception as error:
            raise KpiDefinitionProjectionError(
                'Local KPI Definition projection is invalid'
            ) from error
        if projection.source_key != source_key:
            raise KpiDefinitionProjectionError(
                'Local KPI Definition projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[KpiDefinitionCatalog],
    ) -> ProjectionRecord[KpiDefinitionCatalog]:
        try:
            payload = json.dumps(
                kpi_definition_projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path(projection.source_key), payload)
        except KpiDefinitionProjectionError:
            raise
        except Exception as error:
            raise KpiDefinitionProjectionError(
                'Could not write local KPI Definition projection'
            ) from error
        return projection

    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'kpi_definition_projection_{digest}.json'


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
