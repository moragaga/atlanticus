from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from atlanticus.connectivity.storage import StorageClient

_ID = re.compile(r'[0-9a-f]{32}\Z')


# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosLifecycleAuditError(RuntimeError):
    pass


@runtime_checkable
# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosLifecycleAudit(Protocol):
    # Validación y errores controlados antes de realizar operaciones.
    def record(self, *, action_id: str, stage: str, payload: Mapping[str, object]) -> None: ...


# Contrato pedagógico: responsabilidad aislada y reutilizable.
class BlobCosmosLifecycleAudit:
    # Validación y errores controlados antes de realizar operaciones.
    def __init__(
        self,
        *,
        storage: StorageClient,
        container_name: str,
        blob_prefix: str,
    ) -> None:
        if not isinstance(storage, StorageClient):
            raise TypeError('Cosmos lifecycle audit requires StorageClient')
        if not isinstance(container_name, str) or not container_name.strip():
            raise ValueError('Cosmos lifecycle audit container is required')
        if (
            not isinstance(blob_prefix, str)
            or not blob_prefix
            or blob_prefix != blob_prefix.strip('/')
            or '\\' in blob_prefix
            or any(part in {'', '.', '..'} for part in blob_prefix.split('/'))
        ):
            raise ValueError('Cosmos lifecycle audit prefix is invalid')
        self._storage = storage
        self._container_name = container_name
        self._blob_prefix = blob_prefix

    # Validación y errores controlados antes de realizar operaciones.
    def record(self, *, action_id: str, stage: str, payload: Mapping[str, object]) -> None:
        if not isinstance(action_id, str) or not _ID.fullmatch(action_id):
            raise CosmosLifecycleAuditError('Cosmos lifecycle audit ID is invalid')
        if stage not in {'intent', 'completed', 'failed'}:
            raise CosmosLifecycleAuditError('Cosmos lifecycle audit stage is invalid')
        if not isinstance(payload, Mapping):
            raise CosmosLifecycleAuditError('Cosmos lifecycle audit payload is invalid')
        try:
            content = (json.dumps(dict(payload), sort_keys=True, allow_nan=False) + '\n').encode()
        except (TypeError, ValueError) as error:
            raise CosmosLifecycleAuditError('Cosmos lifecycle audit payload is invalid') from error
        name = f'{self._blob_prefix}/{action_id}/{stage}.json'
        try:
            self._storage.upload(
                container_name=self._container_name,
                blob_name=name,
                data=content,
                overwrite=False,
                content_type='application/json',
            )
            stored = self._storage.download(container_name=self._container_name, blob_name=name)
        except Exception as error:
            raise CosmosLifecycleAuditError('Could not persist Cosmos lifecycle audit') from error
        if stored != content:
            raise CosmosLifecycleAuditError('Cosmos lifecycle audit verification failed')
