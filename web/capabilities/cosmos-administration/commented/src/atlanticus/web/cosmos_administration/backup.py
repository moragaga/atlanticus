from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.cosmos.inventory import CosmosInventory
from atlanticus.connectivity.storage import StorageClient

_QUERY = 'SELECT * FROM c'
_SCHEMA_VERSION = 1
_MANIFEST_LIMIT = 8 * 1024 * 1024
_DEFAULT_PAGE_BYTES = 16 * 1024 * 1024
_BACKUP_ID = re.compile(r'[0-9a-f]{32}\Z')


class CosmosBackupConfigurationError(ValueError):
    pass


class CosmosBackupError(RuntimeError):
    pass


class CosmosBackupIntegrityError(CosmosBackupError):
    pass


@dataclass(frozen=True, slots=True)
class CosmosBackupDestination:
    storage_ref: str
    container_name: str
    blob_prefix: str

    def __post_init__(self) -> None:
        _name(self.storage_ref, 'Storage connection')
        _name(self.container_name, 'Storage container')
        _prefix(self.blob_prefix)


@dataclass(frozen=True, slots=True)
class CosmosBackupReport:
    backup_id: str
    connection_ref: str
    database_name: str
    container_name: str
    destination_ref: str
    manifest_blob_name: str
    document_count: int
    chunk_count: int
    verified: bool
    point_in_time_consistent: bool = False


class _DigestSink:
    def __init__(self) -> None:
        self.size = 0
        self.lines = 0
        self.digest = hashlib.sha256()

    def write(self, content: bytes) -> int:
        self.size += len(content)
        self.lines += content.count(b'\n')
        self.digest.update(content)
        return len(content)

    @property
    def hexdigest(self) -> str:
        return self.digest.hexdigest()


# Coordina Cosmos y Blob mediante conexiones y destinos nombrados de composición.
# No autoriza por sí solo sesiones ROOT: el consumidor Web debe hacerlo.
class CosmosBackupService:
    def __init__(
        self,
        *,
        cosmos_connections: Mapping[str, CosmosClient],
        storage_connections: Mapping[str, StorageClient],
        destinations: Mapping[str, CosmosBackupDestination],
    ) -> None:
        self._cosmos = _connections(cosmos_connections, CosmosClient, 'Cosmos')
        self._storage = _connections(storage_connections, StorageClient, 'Storage')
        if not isinstance(destinations, Mapping) or not destinations:
            raise CosmosBackupConfigurationError('Named backup destinations are required')
        normalized: dict[str, CosmosBackupDestination] = {}
        for name, destination in destinations.items():
            _name(name, 'Backup destination')
            if not isinstance(destination, CosmosBackupDestination):
                raise CosmosBackupConfigurationError('Backup destination definition is invalid')
            if destination.storage_ref not in self._storage:
                raise CosmosBackupConfigurationError('Backup destination storage is not configured')
            normalized[name] = destination
        self._destinations = normalized

    def create_backup(
        self,
        *,
        connection_ref: str,
        container_name: str,
        destination_ref: str,
        operator_id: str,
        page_size: int = 25,
        max_pages: int = 100000,
        max_page_bytes: int = _DEFAULT_PAGE_BYTES,
    ) -> CosmosBackupReport:
        source = self._resolve_source(connection_ref)
        destination, storage = self._resolve_destination(destination_ref)
        _name(container_name, 'Cosmos container')
        _name(operator_id, 'Operator')
        _positive(page_size, 'page_size')
        _positive(max_pages, 'max_pages')
        _positive(max_page_bytes, 'max_page_bytes')
        original = CosmosInventory(client=source).read_container(container_name=container_name)
        backup_id = uuid.uuid4().hex
        base = f'{destination.blob_prefix}/{backup_id}'
        created_at_utc = datetime.now(timezone.utc).isoformat()
        chunks: list[dict[str, Any]] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        read_pages = 0
        document_count = 0
        # Procesar una página por vez; un fallo no publica el manifiesto COMPLETE.
        while True:
            if read_pages >= max_pages:
                raise CosmosBackupError('Cosmos backup exceeded max_pages without completion')
            page = source.query_page(
                container_name=container_name,
                query=_QUERY,
                cross_partition=True,
                page_size=page_size,
                continuation_token=token,
                include_metadata=False,
            )
            read_pages += 1
            if page.items:
                body = _encode_page(page.items, max_page_bytes=max_page_bytes)
                blob_name = f'{base}/chunks/{len(chunks) + 1:08d}.ndjson'
                digest = _upload_verified(
                    storage, destination.container_name, blob_name, body, 'application/x-ndjson'
                )
                chunks.append(
                    {
                        'blob_name': blob_name,
                        'document_count': len(page.items),
                        'bytes': len(body),
                        'sha256': digest,
                    }
                )
                document_count += len(page.items)
            next_token = page.continuation_token
            if next_token is None:
                break
            if next_token == token or next_token in seen_tokens:
                raise CosmosBackupError('Cosmos backup continuation did not advance')
            seen_tokens.add(next_token)
            token = next_token
        # La definición física no debe cambiar durante la captura.
        updated = CosmosInventory(client=source).read_container(container_name=container_name)
        if updated != original:
            raise CosmosBackupError('Cosmos container definition changed during backup')
        # El manifiesto se escribe al final, cuando cada fragmento ya fue releído.
        manifest = {
            'schema_version': _SCHEMA_VERSION,
            'status': 'COMPLETE',
            'backup_id': backup_id,
            'created_at_utc': created_at_utc,
            'completed_at_utc': datetime.now(timezone.utc).isoformat(),
            'requested_by': operator_id,
            'source': {
                'connection_ref': connection_ref,
                'database_name': source.settings.database_name,
                'container_name': container_name,
                'partition_key_paths': list(original.partition_key_paths),
                'default_ttl_seconds': original.default_ttl_seconds,
            },
            'destination_ref': destination_ref,
            'format': 'application/x-ndjson',
            'system_metadata_included': False,
            'point_in_time_consistent': False,
            'read_pages': read_pages,
            'document_count': document_count,
            'chunk_count': len(chunks),
            'chunks': chunks,
        }
        body = _json_bytes(manifest)
        if len(body) > _MANIFEST_LIMIT:
            raise CosmosBackupError('Cosmos backup manifest exceeds allowed size')
        manifest_name = f'{base}/manifest.json'
        _upload_verified(
            storage, destination.container_name, manifest_name, body, 'application/json'
        )
        return CosmosBackupReport(
            backup_id=backup_id,
            connection_ref=connection_ref,
            database_name=source.settings.database_name,
            container_name=container_name,
            destination_ref=destination_ref,
            manifest_blob_name=manifest_name,
            document_count=document_count,
            chunk_count=len(chunks),
            verified=True,
        )

    # La verificación posterior es independiente de la ejecución que creó el respaldo.
    def verify_backup(self, *, destination_ref: str, backup_id: str) -> CosmosBackupReport:
        destination, storage = self._resolve_destination(destination_ref)
        if not isinstance(backup_id, str) or not _BACKUP_ID.fullmatch(backup_id):
            raise CosmosBackupConfigurationError('Backup ID is invalid')
        base = f'{destination.blob_prefix}/{backup_id}'
        manifest_name = f'{base}/manifest.json'
        properties = storage.get_properties(
            container_name=destination.container_name, blob_name=manifest_name
        )
        if properties.size > _MANIFEST_LIMIT or properties.size == 0:
            raise CosmosBackupIntegrityError('Cosmos backup manifest size is invalid')
        body = storage.download(container_name=destination.container_name, blob_name=manifest_name)
        if len(body) != properties.size:
            raise CosmosBackupIntegrityError('Cosmos backup manifest length differs from Blob')
        try:
            manifest = json.loads(body)
        except (ValueError, UnicodeError) as error:
            raise CosmosBackupIntegrityError('Cosmos backup manifest is not valid JSON') from error
        _validate_manifest(manifest, backup_id=backup_id, destination_ref=destination_ref)
        total = 0
        for index, chunk in enumerate(manifest['chunks'], start=1):
            expected_name = f'{base}/chunks/{index:08d}.ndjson'
            if chunk.get('blob_name') != expected_name:
                raise CosmosBackupIntegrityError('Cosmos backup chunk path is invalid')
            sink = _verify_blob(storage, destination.container_name, expected_name)
            if (
                sink.size != chunk.get('bytes')
                or sink.hexdigest != chunk.get('sha256')
                or sink.lines != chunk.get('document_count')
            ):
                raise CosmosBackupIntegrityError('Cosmos backup chunk integrity mismatch')
            total += sink.lines
        if total != manifest['document_count']:
            raise CosmosBackupIntegrityError('Cosmos backup document count mismatch')
        source = manifest['source']
        return CosmosBackupReport(
            backup_id=backup_id,
            connection_ref=source['connection_ref'],
            database_name=source['database_name'],
            container_name=source['container_name'],
            destination_ref=destination_ref,
            manifest_blob_name=manifest_name,
            document_count=total,
            chunk_count=len(manifest['chunks']),
            verified=True,
        )

    def _resolve_source(self, connection_ref: str) -> CosmosClient:
        if not isinstance(connection_ref, str) or connection_ref not in self._cosmos:
            raise CosmosBackupConfigurationError('Cosmos connection is not configured')
        return self._cosmos[connection_ref]

    def _resolve_destination(
        self, destination_ref: str
    ) -> tuple[CosmosBackupDestination, StorageClient]:
        if not isinstance(destination_ref, str) or destination_ref not in self._destinations:
            raise CosmosBackupConfigurationError('Backup destination is not configured')
        destination = self._destinations[destination_ref]
        return destination, self._storage[destination.storage_ref]


def _connections(connections: object, expected_type: type, label: str) -> dict:
    if not isinstance(connections, Mapping) or not connections:
        raise CosmosBackupConfigurationError(f'Named {label} connections are required')
    normalized = {}
    for name, client in connections.items():
        _name(name, f'{label} connection')
        if not isinstance(client, expected_type):
            raise CosmosBackupConfigurationError(f'{label} connection has an invalid client')
        normalized[name] = client
    return normalized


def _name(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 255
        or any(ord(char) < 32 for char in value)
    ):
        raise CosmosBackupConfigurationError(f'{field_name} is invalid')


def _prefix(value: str) -> None:
    _name(value, 'Backup Blob prefix')
    if (
        value.startswith('/')
        or value.endswith('/')
        or '\\' in value
        or any(part in {'', '.', '..'} for part in value.split('/'))
        or any(char in value for char in '?#')
    ):
        raise CosmosBackupConfigurationError('Backup Blob prefix is invalid')


def _positive(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CosmosBackupConfigurationError(f'{label} must be a positive integer')


def _json_bytes(value: object) -> bytes:
    try:
        content = json.dumps(
            value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False
        )
        return (content + '\n').encode('utf-8')
    except (ValueError, TypeError) as error:
        raise CosmosBackupError('Cosmos backup contains non-JSON values') from error


# NDJSON conserva cada documento como una línea y limita memoria por página.
def _encode_page(items: tuple[dict[str, Any], ...], *, max_page_bytes: int) -> bytes:
    parts: list[bytes] = []
    size = 0
    for document in items:
        if (
            not isinstance(document, dict)
            or not isinstance(document.get('id'), str)
            or not document['id']
        ):
            raise CosmosBackupError('Cosmos backup item has an invalid id')
        content = _json_bytes(document)
        size += len(content)
        if size > max_page_bytes:
            raise CosmosBackupError('Cosmos backup page exceeds max_page_bytes; reduce page_size')
        parts.append(content)
    return b''.join(parts)


def _verify_blob(storage: StorageClient, container_name: str, blob_name: str) -> _DigestSink:
    sink = _DigestSink()
    received = storage.download_to(container_name=container_name, blob_name=blob_name, target=sink)
    if received != sink.size:
        raise CosmosBackupIntegrityError('Cosmos backup Blob length mismatch')
    return sink


# El hash se calcula localmente y se contrasta con lo realmente descargado del Blob.
def _upload_verified(
    storage: StorageClient, container_name: str, blob_name: str, content: bytes, content_type: str
) -> str:
    expected = hashlib.sha256(content).hexdigest()
    storage.upload(
        container_name=container_name,
        blob_name=blob_name,
        data=content,
        overwrite=False,
        content_type=content_type,
    )
    sink = _verify_blob(storage, container_name, blob_name)
    if sink.size != len(content) or sink.hexdigest != expected:
        raise CosmosBackupIntegrityError('Cosmos backup Blob verification failed')
    return expected


def _validate_manifest(manifest: object, *, backup_id: str, destination_ref: str) -> None:
    if not isinstance(manifest, dict):
        raise CosmosBackupIntegrityError('Cosmos backup manifest is invalid')
    if (
        manifest.get('schema_version') != _SCHEMA_VERSION
        or manifest.get('status') != 'COMPLETE'
        or manifest.get('backup_id') != backup_id
        or manifest.get('destination_ref') != destination_ref
        or manifest.get('point_in_time_consistent') is not False
        or manifest.get('system_metadata_included') is not False
        or manifest.get('format') != 'application/x-ndjson'
    ):
        raise CosmosBackupIntegrityError('Cosmos backup manifest contract is invalid')
    source = manifest.get('source')
    if not isinstance(source, dict):
        raise CosmosBackupIntegrityError('Cosmos backup source metadata is invalid')
    for key in ('connection_ref', 'database_name', 'container_name'):
        value = source.get(key)
        if not isinstance(value, str) or not value:
            raise CosmosBackupIntegrityError('Cosmos backup source metadata is invalid')
    if (
        not isinstance(source.get('partition_key_paths'), list)
        or not source['partition_key_paths']
        or any(
            not isinstance(path, str) or not path.startswith('/')
            for path in source['partition_key_paths']
        )
    ):
        raise CosmosBackupIntegrityError('Cosmos backup partition keys are invalid')
    if (
        not isinstance(manifest.get('chunks'), list)
        or not isinstance(manifest.get('chunk_count'), int)
        or isinstance(manifest['chunk_count'], bool)
        or len(manifest['chunks']) != manifest['chunk_count']
        or not isinstance(manifest.get('document_count'), int)
        or isinstance(manifest['document_count'], bool)
        or manifest['document_count'] < 0
    ):
        raise CosmosBackupIntegrityError('Cosmos backup counters are invalid')
    for chunk in manifest['chunks']:
        if (
            not isinstance(chunk, dict)
            or not isinstance(chunk.get('sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', chunk['sha256'])
        ):
            raise CosmosBackupIntegrityError('Cosmos backup chunk descriptor is invalid')
        for name in ('document_count', 'bytes'):
            if type(chunk.get(name)) is not int or chunk[name] <= 0:
                raise CosmosBackupIntegrityError('Cosmos backup chunk counters are invalid')
