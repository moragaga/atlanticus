# Adaptador Cosmos exclusivo del dominio ADA sobre un contenedor inyectado; admite convivencia física con users-support.
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, Protocol

from ada.web.operational.identification.errors import (
    OperationalIdentificationError,
    OperationalPersistenceError,
)
from ada.web.operational.identification.keys import source_kind
from ada.web.operational.identification.models import OperationalDocument
from ada.web.operational.identification.projection import (
    projection_from_document,
    projection_to_document,
)
from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


class _CosmosClient(Protocol):
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, Any] | None: ...

    def create_item(self, *, container_name: str, item: Mapping[str, Any]) -> dict[str, Any]: ...

    def patch_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        operations: tuple[CosmosPatchOperation, ...],
        if_match_etag: str | None = None,
    ) -> dict[str, Any]: ...


# Escrituras condicionales por ETag evitan sobreescrituras secuenciales obsoletas.
class CosmosOperationalProjectionStore(ProjectionStore[OperationalDocument]):
    def __init__(self, *, client: _CosmosClient, container_name: str) -> None:
        if not isinstance(container_name, str) or not container_name.strip():
            raise ValueError('Operational Cosmos container name is invalid')
        if container_name != container_name.strip():
            raise ValueError('Operational Cosmos container name is invalid')
        self._client = client
        self._container = container_name

    # Lectura puntual mediante el par id + partition_key, sin escaneo de users-support.
    def get_active(self, source_key: SourceKey) -> ProjectionRecord[OperationalDocument] | None:
        source_kind(source_key)
        try:
            document = self._client.find_item(
                container_name=self._container,
                item_id=_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise OperationalPersistenceError('Could not read operational projection') from error
        return None if document is None else self._decode(document, source_key)

    # Solo se modifica el documento del usuario o catálogo afectado; reintentos limitados.
    def replace_active(
        self,
        record: ProjectionRecord[OperationalDocument],
    ) -> ProjectionRecord[OperationalDocument]:
        source_kind(record.source_key)
        item_id = _item_id(record.source_key)
        document = projection_to_document(record, item_id=item_id)
        for _ in range(3):
            try:
                current = self._client.find_item(
                    container_name=self._container,
                    item_id=item_id,
                    partition_key=record.source_key.value,
                    include_metadata=True,
                )
                if current is None:
                    saved = self._client.create_item(container_name=self._container, item=document)
                else:
                    previous = self._decode(current, record.source_key)
                    if previous.source_published_at_utc > record.source_published_at_utc:
                        raise OperationalPersistenceError(
                            'A newer operational projection is active'
                        )
                    if previous.source_published_at_utc == record.source_published_at_utc:
                        if previous.target == record.target and previous.payload == record.payload:
                            return previous
                        raise OperationalPersistenceError(
                            'Operational source version is inconsistent'
                        )
                    etag = current.get('_etag')
                    if not isinstance(etag, str) or not etag:
                        raise OperationalPersistenceError('Operational projection ETag is missing')
                    saved = self._client.patch_item(
                        container_name=self._container,
                        item_id=item_id,
                        partition_key=record.source_key.value,
                        operations=tuple(
                            CosmosPatchOperation(operation='set', path=f'/{key}', value=value)
                            for key, value in document.items()
                            if key not in {'id', 'partition_key'}
                        ),
                        if_match_etag=etag,
                    )
                result = self._decode(saved, record.source_key)
                if result.target != record.target or result.payload != record.payload:
                    raise OperationalPersistenceError('Cosmos persisted different operational data')
                return result
            except CosmosConflictError, CosmosPreconditionFailedError:
                continue
            except CosmosError as error:
                raise OperationalPersistenceError(
                    'Could not write operational projection'
                ) from error
        raise OperationalPersistenceError('Operational projection changed concurrently')

    @staticmethod
    def _decode(
        document: dict[str, Any],
        source_key: SourceKey,
    ) -> ProjectionRecord[OperationalDocument]:
        if document.get('id') != _item_id(source_key):
            raise OperationalIdentificationError('Operational projection id is invalid')
        result = projection_from_document(document)
        if result.source_key != source_key:
            raise OperationalIdentificationError('Operational projection source key is invalid')
        return result


def _item_id(source_key: SourceKey) -> str:
    source_kind(source_key)
    return 'ada-operational-' + hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
