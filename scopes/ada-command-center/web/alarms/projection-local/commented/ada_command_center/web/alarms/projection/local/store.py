# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from ada_command_center.web.alarms.configuration.projection_record import (
    alarm_configuration_projection_from_document,
    alarm_configuration_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class LocalAlarmConfigurationProjectionStoreSettings:
    root: Path

    def __post_init__(self) -> None:
        path = Path(self.root).expanduser()
        if not path.is_absolute():
            raise ValueError('Local Alarm Configuration projection root must be absolute')
        object.__setattr__(self, 'root', path)


# El archivo representa únicamente el head activo, no una copia del historial Source.
class LocalAlarmConfigurationProjectionStore(ProjectionStore[AlarmConfigurationSnapshot]):
    def __init__(self, settings: LocalAlarmConfigurationProjectionStoreSettings) -> None:
        if not isinstance(settings, LocalAlarmConfigurationProjectionStoreSettings):
            raise TypeError('settings must be LocalAlarmConfigurationProjectionStoreSettings')
        self._settings = settings

    # Ausente devuelve None; errores de lectura o datos corruptos se propagan como errores de proyección.
    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[AlarmConfigurationSnapshot] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            projection = alarm_configuration_projection_from_document(document)
        except AlarmConfigurationProjectionError:
            raise
        except (OSError, ValueError, TypeError) as error:
            raise AlarmConfigurationProjectionError(
                'Could not read local Alarm Configuration projection'
            ) from error
        if projection.source_key != source_key:
            raise AlarmConfigurationProjectionError(
                'Local Alarm Configuration projection source key does not match request'
            )
        return projection

    # Se sustituye el head activo para un SourceKey; la selección de la release pertenece al servicio genérico.
    def replace_active(
        self,
        projection: ProjectionRecord[AlarmConfigurationSnapshot],
    ) -> ProjectionRecord[AlarmConfigurationSnapshot]:
        try:
            payload = json.dumps(
                alarm_configuration_projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path(projection.source_key), payload)
        except AlarmConfigurationProjectionError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise AlarmConfigurationProjectionError(
                'Could not write local Alarm Configuration projection'
            ) from error
        return projection

    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'alarm_configuration_projection_{digest}.json'


# Archivo temporal, fsync y replace evitan observar escrituras parciales durante recuperación local.
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
