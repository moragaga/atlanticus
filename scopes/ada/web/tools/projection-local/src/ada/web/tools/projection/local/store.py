from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.configuration.errors import ToolConfigurationProjectionError
from ada.web.tools.configuration.projection_record import (
    tool_projection_from_document,
    tool_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class LocalToolProjectionStoreSettings:
    root: Path

    @classmethod
    def from_namespace(
        cls,
        *,
        namespace: AdaStorageNamespace,
        base_root: str | Path,
    ) -> LocalToolProjectionStoreSettings:
        if not isinstance(namespace, AdaStorageNamespace):
            raise TypeError('namespace must be AdaStorageNamespace')
        return cls(root=namespace.local_projection_root(base_root))


class LocalToolProjectionStore(ProjectionStore[ToolConfiguration]):
    def __init__(self, settings: LocalToolProjectionStoreSettings) -> None:
        if not isinstance(settings, LocalToolProjectionStoreSettings):
            raise TypeError('settings must be LocalToolProjectionStoreSettings')
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[ToolConfiguration] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            projection = tool_projection_from_document(document)
        except ToolConfigurationProjectionError:
            raise
        except Exception as error:
            raise ToolConfigurationProjectionError('Local Tool projection is invalid') from error
        if projection.source_key != source_key:
            raise ToolConfigurationProjectionError(
                'Local Tool projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[ToolConfiguration],
    ) -> ProjectionRecord[ToolConfiguration]:
        try:
            payload = json.dumps(
                tool_projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(
                self._path(projection.source_key),
                payload,
            )
        except ToolConfigurationProjectionError:
            raise
        except Exception as error:
            raise ToolConfigurationProjectionError(
                'Could not write local Tool projection'
            ) from error
        return projection

    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'tool_projection_{digest}.json'


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
