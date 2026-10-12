# El transporte asigna un ID estable a cada Tool y utiliza clientes Cosmos separados en un pool acotado.
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

from ada.processes.alarm_delivery.contract import ToolDeliveryCandidate
from ada.processes.alarm_delivery.public_projection import (
    LIVE_PUBLIC_SCHEMA_VERSION,
    public_tool_projection,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings

LIVE_CONTAINER = 'alarm-live-projection'
LIVE_PARTITION_KEY = '/tool_key'
LIVE_DOCUMENT_TYPE = 'ada_alarm_live_tool_projection'
LIVE_SCHEMA_VERSION = LIVE_PUBLIC_SCHEMA_VERSION


# Responsabilidad delimitada: CosmosWriter
class CosmosWriter(Protocol):
    # Método del componente: __enter__
    def __enter__(self) -> CosmosWriter: ...

    # Método del componente: __exit__
    def __exit__(self, *_: object) -> None: ...

    # Método del componente: upsert_item
    def upsert_item(self, *, container_name: str, item: Mapping[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
# Responsabilidad delimitada: ToolPublishResult
class ToolPublishResult:
    tool_key: str
    successful: bool
    error_type: str | None = None


# La identidad del destino no contiene secretos: sólo endpoint, base y contenedor.
def destination_identity(settings: CosmosSettings) -> str:
    if not isinstance(settings, CosmosSettings):
        raise TypeError('Destination must be CosmosSettings')
    identifier = {
        'endpoint': settings.endpoint,
        'database_name': settings.database_name,
        'container_name': LIVE_CONTAINER,
    }
    return hashlib.sha256(
        json.dumps(identifier, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


# Construye el contrato físico que consume ADA sin volver a resolver catálogos.
def live_document(candidate: ToolDeliveryCandidate) -> dict[str, object]:
    if not isinstance(candidate, ToolDeliveryCandidate):
        raise TypeError('Live publication requires a ToolDeliveryCandidate')
    tool = candidate.tool
    if tool.get('tool_key') != candidate.tool_key:
        raise ValueError('Live publication Tool identity differs')
    presentation = public_tool_projection(tool)
    return {
        'id': f'alarm-live:{candidate.tool_key}',
        'document_type': LIVE_DOCUMENT_TYPE,
        'schema_version': LIVE_SCHEMA_VERSION,
        'tool_key': candidate.tool_key,
        **presentation,
        'resolution_key': dict(candidate.artifact_ref['resolution_key']),
        'source_as_of': candidate.source_as_of,
        'source_sha256': candidate.source_sha256,
        'semantic_sha256': candidate.semantic_sha256,
    }


# Responsabilidad delimitada: ParallelCosmosPublisher
class ParallelCosmosPublisher:
    # Método del componente: __init__
    def __init__(
        self,
        *,
        connections: Mapping[str, CosmosSettings],
        max_workers: int,
        client_factory: Callable[[CosmosSettings], CosmosWriter] | None = None,
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
            raise ValueError('max_workers must be a positive integer')
        self._connections = dict(connections)
        self._factory = client_factory or (lambda settings: CosmosClient(settings=settings))
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='alarm-live'
        )
        self._closed = False

    # Método del componente: close
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True)

    # Todas las tareas terminan antes de devolver resultados por Tool; fallos quedan aislados.
    def publish(
        self,
        candidates: tuple[ToolDeliveryCandidate, ...],
        *,
        assert_authority: Callable[[], None],
    ) -> tuple[ToolPublishResult, ...]:
        if self._closed:
            raise RuntimeError('Delivery publisher is closed')
        if not callable(assert_authority):
            raise TypeError('assert_authority must be callable')
        if not isinstance(candidates, tuple) or any(
            not isinstance(item, ToolDeliveryCandidate) for item in candidates
        ):
            raise TypeError('Candidates must be ToolDeliveryCandidate values')
        if len({item.tool_key for item in candidates}) != len(candidates):
            raise ValueError('Only one delivery candidate per Tool is allowed')
        if any(item.tool_key not in self._connections for item in candidates):
            raise ValueError('A Delivery candidate has an unknown Cosmos destination')
        for item in candidates:
            if item.destination_identity != destination_identity(self._connections[item.tool_key]):
                raise ValueError('Delivery destination identity changed')
        if not candidates:
            return ()
        documents = {item.tool_key: live_document(item) for item in candidates}
        assert_authority()
        futures = {
            self._executor.submit(
                self._publish_one, item.tool_key, documents[item.tool_key], assert_authority
            ): item.tool_key
            for item in candidates
        }
        results = []
        for future in as_completed(futures):
            key = futures[future]
            try:
                future.result()
                results.append(ToolPublishResult(tool_key=key, successful=True))
            except Exception as error:
                results.append(
                    ToolPublishResult(
                        tool_key=key, successful=False, error_type=type(error).__name__
                    )
                )
        assert_authority()
        return tuple(sorted(results, key=lambda item: item.tool_key))

    # Cada hilo crea y cierra un cliente y verifica la autoridad de ejecución.
    def _publish_one(
        self, tool_key: str, document: Mapping[str, object], assert_authority: Callable[[], None]
    ) -> None:
        assert_authority()
        with self._factory(self._connections[tool_key]) as client:
            client.upsert_item(container_name=LIVE_CONTAINER, item=document)
        assert_authority()
