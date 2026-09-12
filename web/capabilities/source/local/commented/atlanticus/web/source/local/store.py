# Este módulo implementa el proveedor durable Local de Source.
# La publicación materializa una release inmutable y solo se vuelve vigente al promover manifest.json.
from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlanticus.web.source.errors import (
    SourceConcurrencyError,
    SourceCorruptionError,
    SourceReleaseNotFoundError,
    SourceUnavailableError,
)
from atlanticus.web.source.local._codec import (
    SCHEMA_VERSION,
    content_hash,
    decode_cursor,
    encode_cursor,
    manifest_from_bytes,
    manifest_to_bytes,
    release_metadata_from_bytes,
    release_metadata_to_bytes,
    resource_metadata,
    token_for_manifest,
)
from atlanticus.web.source.local._filesystem import (
    SourceFileLock,
    atomic_write_bytes,
    encode_segment,
    fsync_directory,
    remove_temporary_tree,
    write_new_bytes,
)
from atlanticus.web.source.models import (
    HistoryPage,
    HistoryQuery,
    IntegrityFailure,
    IntegrityResult,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceManifest,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceResource,
    SourceResourceMetadata,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore


@dataclass(frozen=True, slots=True)
# Configuración del provider Local: solo necesita una raíz física controlada por el consumidor.
class LocalSourceSettings:
    root: Path


# Implementación local durable que replica el contrato de publicación que luego tendrá Blob.
class LocalSourceStore(SourceStore):
    def __init__(
        self,
        settings: LocalSourceSettings,
        *,
        clock: Callable[[], datetime] | None = None,
        release_id_factory: Callable[[], SourceReleaseId] | None = None,
    ) -> None:
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._release_id_factory = release_id_factory or (
            lambda: SourceReleaseId(uuid.uuid4().hex)
        )

    # Lee manifest de forma atómica: ausencia significa Source todavía no publicada.
    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        try:
            manifest_path = self._manifest_path(source_key)
            if not manifest_path.exists():
                return SourceSnapshot(source_key, None, None)
            payload = manifest_path.read_bytes()
            manifest = manifest_from_bytes(payload)
            if manifest.source_key != source_key:
                raise SourceCorruptionError('Source manifest key does not match requested source')
            return SourceSnapshot(
                source_key=source_key,
                current=manifest.current,
                concurrency_token=token_for_manifest(payload),
            )
        except SourceCorruptionError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise SourceCorruptionError('Source manifest is invalid') from error
        except OSError as error:
            raise SourceUnavailableError('Could not read local source manifest') from error

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        integrity = self.verify_release(source_key, release_ref)
        if not integrity.valid:
            raise SourceCorruptionError('Source release failed integrity verification')
        metadata = self._read_release_metadata(source_key, release_ref)
        resources: list[SourceResource] = []
        try:
            release_directory = self._release_directory(source_key, release_ref)
            for resource in metadata.resources:
                resource_path = release_directory / 'resources' / Path(resource.logical_path)
                resources.append(SourceResource(resource.logical_path, resource_path.read_bytes()))
        except FileNotFoundError as error:
            raise SourceCorruptionError('Source release resource is missing') from error
        except OSError as error:
            raise SourceUnavailableError('Could not read local source release') from error
        return metadata, tuple(resources)

    # Materializa primero; después compara el token bajo lock y solo entonces reemplaza manifest.
    def publish(self, request: PublishRequest) -> PublishResult:
        observed = self.get_current(request.source_key)
        if observed.concurrency_token != request.expected_concurrency_token:
            raise SourceConcurrencyError('Source changed before publication started')

        previous_ref = observed.current.release_ref if observed.current is not None else None
        release_ref = SourceReleaseRef(
            release_id=self._release_id_factory(),
            published_at_utc=self._publication_time(previous_ref),
        )
        metadata = self._materialize_candidate(request, release_ref, previous_ref)
        integrity = self.verify_release(request.source_key, release_ref)
        if not integrity.valid:
            raise SourceCorruptionError('Materialized source release failed integrity verification')

        manifest = SourceManifest(
            schema_version=SCHEMA_VERSION,
            source_key=request.source_key,
            current=SourceReleaseSummary(release_ref, metadata.content_hash),
        )
        manifest_payload = manifest_to_bytes(manifest)

        try:
            with SourceFileLock(self._lock_path(request.source_key)):
                current = self.get_current(request.source_key)
                if current.concurrency_token != request.expected_concurrency_token:
                    raise SourceConcurrencyError('Source changed before publication promotion')
                atomic_write_bytes(self._manifest_path(request.source_key), manifest_payload)
        except SourceConcurrencyError:
            raise
        except OSError as error:
            raise SourceUnavailableError('Could not promote local source release') from error

        snapshot = SourceSnapshot(
            source_key=request.source_key,
            current=manifest.current,
            concurrency_token=token_for_manifest(manifest_payload),
        )
        return PublishResult(release=metadata, snapshot=snapshot)

    # Recorre únicamente previous_published_release; nunca lista carpetas para inventar History.
    def query_history(self, query: HistoryQuery) -> HistoryPage:
        snapshot = self.get_current(query.source_key)
        if query.cursor is not None:
            current_ref = decode_cursor(query.cursor, query.source_key)
        elif snapshot.current is not None:
            current_ref = snapshot.current.release_ref
        else:
            return HistoryPage(())

        items: list[SourceReleaseSummary] = []
        next_cursor: str | None = None
        while current_ref is not None:
            metadata = self._read_release_metadata(query.source_key, current_ref)
            next_ref = metadata.previous_published_release
            published_at = metadata.release_ref.published_at_utc
            in_lower_bound = (
                query.published_from_utc is None or published_at >= query.published_from_utc
            )
            in_upper_bound = query.published_to_utc is None or published_at <= query.published_to_utc
            if in_lower_bound and in_upper_bound:
                items.append(SourceReleaseSummary(metadata.release_ref, metadata.content_hash))
                if len(items) == query.page_size:
                    if next_ref is not None:
                        next_cursor = encode_cursor(query.source_key, next_ref)
                    break
            current_ref = next_ref

        return HistoryPage(tuple(items), next_cursor)

    # Verifica metadata, presencia, tamaño, digest y hash agregado sin cambiar Source.
    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        release_directory = self._release_directory(source_key, release_ref)
        if not release_directory.exists():
            raise SourceReleaseNotFoundError(
                f'Source release not found: {release_ref.release_id.value}'
            )

        failures: list[IntegrityFailure] = []
        try:
            metadata = release_metadata_from_bytes((release_directory / 'release.json').read_bytes())
            if metadata.source_key != source_key or metadata.release_ref != release_ref:
                failures.append(
                    IntegrityFailure(
                        'invalid_metadata',
                        'Source release metadata does not match requested release',
                    )
                )
                return IntegrityResult(release_ref, 0, tuple(failures))
        except FileNotFoundError:
            failures.append(
                IntegrityFailure('invalid_metadata', 'Source release metadata is missing')
            )
            return IntegrityResult(release_ref, 0, tuple(failures))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            failures.append(
                IntegrityFailure('invalid_metadata', 'Source release metadata is invalid')
            )
            return IntegrityResult(release_ref, 0, tuple(failures))
        except OSError as error:
            raise SourceUnavailableError('Could not verify local source release') from error

        checked = 0
        actual_metadata: list[SourceResourceMetadata] = []
        for expected in metadata.resources:
            path = release_directory / 'resources' / Path(expected.logical_path)
            try:
                content = path.read_bytes()
            except FileNotFoundError:
                failures.append(
                    IntegrityFailure(
                        'missing_resource',
                        'Source release resource is missing',
                        expected.logical_path,
                    )
                )
                continue
            except OSError as error:
                raise SourceUnavailableError('Could not verify local source resource') from error

            checked += 1
            actual = resource_metadata(expected.logical_path, content)
            actual_metadata.append(actual)
            if actual.byte_length != expected.byte_length:
                failures.append(
                    IntegrityFailure(
                        'size_mismatch',
                        'Source release resource size does not match metadata',
                        expected.logical_path,
                    )
                )
            if actual.digest != expected.digest:
                failures.append(
                    IntegrityFailure(
                        'digest_mismatch',
                        'Source release resource digest does not match metadata',
                        expected.logical_path,
                    )
                )

        if len(actual_metadata) == len(metadata.resources):
            actual_content_hash = content_hash(tuple(actual_metadata))
            if actual_content_hash != metadata.content_hash:
                failures.append(
                    IntegrityFailure(
                        'content_hash_mismatch',
                        'Source release content hash does not match resources',
                    )
                )

        return IntegrityResult(release_ref, checked, tuple(failures))

    # Escribe la release en un directorio temporal y la vuelve inmutable mediante rename.
    def _materialize_candidate(
        self,
        request: PublishRequest,
        release_ref: SourceReleaseRef,
        previous_ref: SourceReleaseRef | None,
    ) -> SourceReleaseMetadata:
        resource_inventory = tuple(
            sorted(
                (resource_metadata(item.logical_path, item.content) for item in request.resources),
                key=lambda item: item.logical_path,
            )
        )
        metadata = SourceReleaseMetadata(
            schema_version=SCHEMA_VERSION,
            source_key=request.source_key,
            release_ref=release_ref,
            content_hash=content_hash(resource_inventory),
            resources=resource_inventory,
            previous_published_release=previous_ref,
            basis_release=request.basis_release,
        )
        release_directory = self._release_directory(request.source_key, release_ref)
        temporary = release_directory.parent / f'.{release_directory.name}.tmp-{uuid.uuid4().hex}'
        try:
            if release_directory.exists():
                raise SourceCorruptionError('Generated source release id already exists')
            temporary.mkdir(parents=True, exist_ok=False)
            resources_by_path = {item.logical_path: item for item in request.resources}
            for item in resource_inventory:
                resource_path = temporary / 'resources' / Path(item.logical_path)
                write_new_bytes(resource_path, resources_by_path[item.logical_path].content)
            write_new_bytes(temporary / 'release.json', release_metadata_to_bytes(metadata))
            fsync_directory(temporary)
            release_directory.parent.mkdir(parents=True, exist_ok=True)
            os.rename(temporary, release_directory)
            fsync_directory(release_directory.parent)
        except SourceCorruptionError:
            raise
        except OSError as error:
            raise SourceUnavailableError('Could not materialize local source release') from error
        finally:
            if temporary.exists():
                remove_temporary_tree(temporary)
        return metadata

    def _read_release_metadata(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> SourceReleaseMetadata:
        release_directory = self._release_directory(source_key, release_ref)
        if not release_directory.exists():
            raise SourceReleaseNotFoundError(
                f'Source release not found: {release_ref.release_id.value}'
            )
        try:
            metadata = release_metadata_from_bytes((release_directory / 'release.json').read_bytes())
        except FileNotFoundError as error:
            raise SourceCorruptionError('Source release metadata is missing') from error
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise SourceCorruptionError('Source release metadata is invalid') from error
        except OSError as error:
            raise SourceUnavailableError('Could not read local source release metadata') from error
        if metadata.source_key != source_key or metadata.release_ref != release_ref:
            raise SourceCorruptionError('Source release metadata does not match requested release')
        return metadata

    def _publication_time(self, previous_ref: SourceReleaseRef | None) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError('Local source clock must return a timezone-aware datetime')
        current = current.astimezone(timezone.utc)
        if previous_ref is not None and current <= previous_ref.published_at_utc:
            return previous_ref.published_at_utc + timedelta(microseconds=1)
        return current

    def _source_directory(self, source_key: SourceKey) -> Path:
        return self._settings.root / 'sources' / encode_segment(source_key.value)

    def _manifest_path(self, source_key: SourceKey) -> Path:
        return self._source_directory(source_key) / 'manifest.json'

    def _lock_path(self, source_key: SourceKey) -> Path:
        return self._source_directory(source_key) / '.source.lock'

    def _release_directory(self, source_key: SourceKey, release_ref: SourceReleaseRef) -> Path:
        published_at = release_ref.published_at_utc
        return (
            self._source_directory(source_key)
            / 'history'
            / f'year={published_at.year:04d}'
            / f'month={published_at.month:02d}'
            / f'day={published_at.day:02d}'
            / encode_segment(release_ref.release_id.value)
        )
