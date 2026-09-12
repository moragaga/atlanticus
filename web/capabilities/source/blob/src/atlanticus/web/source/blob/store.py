from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageClient,
    StorageConflictError,
    StorageConnectionError,
    StorageError,
    StorageOperationError,
)
from atlanticus.web.source._codec import (
    SCHEMA_VERSION,
    content_hash,
    decode_cursor,
    encode_cursor,
    encode_segment,
    manifest_from_bytes,
    manifest_to_bytes,
    release_metadata_from_bytes,
    release_metadata_to_bytes,
    resource_metadata,
    token_for_manifest,
)
from atlanticus.web.source.errors import (
    SourceConcurrencyError,
    SourceCorruptionError,
    SourceReleaseNotFoundError,
    SourceUnavailableError,
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
class BlobSourceSettings:
    container_name: str
    root_prefix: str = ''

    def __post_init__(self) -> None:
        container_name = _require_container_name(self.container_name)
        root_prefix = _normalize_root_prefix(self.root_prefix)
        object.__setattr__(self, 'container_name', container_name)
        object.__setattr__(self, 'root_prefix', root_prefix)


@dataclass(frozen=True, slots=True)
class _ObservedSource:
    snapshot: SourceSnapshot
    etag: str | None


class BlobSourceStore(SourceStore):
    def __init__(
        self,
        settings: BlobSourceSettings,
        *,
        storage: StorageClient,
        clock: Callable[[], datetime] | None = None,
        release_id_factory: Callable[[], SourceReleaseId] | None = None,
    ) -> None:
        if not isinstance(settings, BlobSourceSettings):
            raise TypeError('settings must be BlobSourceSettings')
        self._settings = settings
        self._storage = storage
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._release_id_factory = release_id_factory or (lambda: SourceReleaseId(uuid.uuid4().hex))

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        return self._observe_current(source_key).snapshot

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
            for resource in metadata.resources:
                payload = self._storage.download(
                    container_name=self._settings.container_name,
                    blob_name=self._resource_blob_name(
                        source_key,
                        release_ref,
                        resource.logical_path,
                    ),
                )
                resources.append(SourceResource(resource.logical_path, payload))
        except StorageBlobNotFoundError as error:
            raise SourceCorruptionError('Source release resource is missing') from error
        except StorageError as error:
            raise SourceUnavailableError('Could not read Blob source release') from error
        return metadata, tuple(resources)

    def publish(self, request: PublishRequest) -> PublishResult:
        observed = self._observe_current(request.source_key)
        if observed.snapshot.concurrency_token != request.expected_concurrency_token:
            raise SourceConcurrencyError('Source changed before publication started')

        previous_ref = (
            observed.snapshot.current.release_ref if observed.snapshot.current is not None else None
        )
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
        candidate_snapshot = SourceSnapshot(
            source_key=request.source_key,
            current=manifest.current,
            concurrency_token=token_for_manifest(manifest_payload),
        )

        try:
            self._promote_manifest(
                source_key=request.source_key,
                payload=manifest_payload,
                observed_etag=observed.etag,
            )
        except StorageConflictError as error:
            raise SourceConcurrencyError('Source changed before publication promotion') from error
        except (StorageConnectionError, StorageOperationError) as error:
            return self._recover_ambiguous_promotion(
                request=request,
                metadata=metadata,
                expected_snapshot=observed.snapshot,
                candidate_snapshot=candidate_snapshot,
                error=error,
            )
        except StorageError as error:
            raise SourceUnavailableError('Could not promote Blob source release') from error

        return PublishResult(release=metadata, snapshot=candidate_snapshot)

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
            in_upper_bound = (
                query.published_to_utc is None or published_at <= query.published_to_utc
            )
            if in_lower_bound and in_upper_bound:
                items.append(SourceReleaseSummary(metadata.release_ref, metadata.content_hash))
                if len(items) == query.page_size:
                    if next_ref is not None:
                        next_cursor = encode_cursor(query.source_key, next_ref)
                    break
            current_ref = next_ref

        return HistoryPage(tuple(items), next_cursor)

    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        try:
            payload = self._storage.download(
                container_name=self._settings.container_name,
                blob_name=self._release_metadata_blob_name(source_key, release_ref),
            )
        except StorageBlobNotFoundError as error:
            raise SourceReleaseNotFoundError(
                f'Source release not found: {release_ref.release_id.value}'
            ) from error
        except StorageError as error:
            raise SourceUnavailableError('Could not verify Blob source release') from error

        failures: list[IntegrityFailure] = []
        try:
            metadata = release_metadata_from_bytes(payload)
            if metadata.source_key != source_key or metadata.release_ref != release_ref:
                failures.append(
                    IntegrityFailure(
                        'invalid_metadata',
                        'Source release metadata does not match requested release',
                    )
                )
                return IntegrityResult(release_ref, 0, tuple(failures))
        except ValueError, TypeError, KeyError, json.JSONDecodeError:
            failures.append(
                IntegrityFailure('invalid_metadata', 'Source release metadata is invalid')
            )
            return IntegrityResult(release_ref, 0, tuple(failures))

        checked = 0
        actual_metadata: list[SourceResourceMetadata] = []
        for expected in metadata.resources:
            try:
                content = self._storage.download(
                    container_name=self._settings.container_name,
                    blob_name=self._resource_blob_name(
                        source_key,
                        release_ref,
                        expected.logical_path,
                    ),
                )
            except StorageBlobNotFoundError:
                failures.append(
                    IntegrityFailure(
                        'missing_resource',
                        'Source release resource is missing',
                        expected.logical_path,
                    )
                )
                continue
            except StorageError as error:
                raise SourceUnavailableError('Could not verify Blob source resource') from error

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

    def _observe_current(self, source_key: SourceKey) -> _ObservedSource:
        blob_name = self._manifest_blob_name(source_key)
        try:
            properties = self._storage.get_properties(
                container_name=self._settings.container_name,
                blob_name=blob_name,
            )
        except StorageBlobNotFoundError:
            return _ObservedSource(SourceSnapshot(source_key, None, None), None)
        except StorageError as error:
            raise SourceUnavailableError(
                'Could not read Blob source manifest properties'
            ) from error

        etag = properties.etag
        if not isinstance(etag, str) or not etag.strip():
            raise SourceUnavailableError('Blob source manifest ETag is unavailable')

        try:
            payload = self._storage.download(
                container_name=self._settings.container_name,
                blob_name=blob_name,
            )
        except StorageBlobNotFoundError as error:
            raise SourceUnavailableError('Blob source manifest changed while being read') from error
        except StorageError as error:
            raise SourceUnavailableError('Could not read Blob source manifest') from error

        try:
            manifest = manifest_from_bytes(payload)
            if manifest.source_key != source_key:
                raise SourceCorruptionError('Source manifest key does not match requested source')
            snapshot = SourceSnapshot(
                source_key=source_key,
                current=manifest.current,
                concurrency_token=token_for_manifest(payload),
            )
        except SourceCorruptionError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise SourceCorruptionError('Source manifest is invalid') from error
        return _ObservedSource(snapshot, etag)

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
        resources_by_path = {item.logical_path: item for item in request.resources}
        try:
            for item in resource_inventory:
                self._storage.upload(
                    container_name=self._settings.container_name,
                    blob_name=self._resource_blob_name(
                        request.source_key,
                        release_ref,
                        item.logical_path,
                    ),
                    data=resources_by_path[item.logical_path].content,
                    overwrite=False,
                )
            self._storage.upload(
                container_name=self._settings.container_name,
                blob_name=self._release_metadata_blob_name(request.source_key, release_ref),
                data=release_metadata_to_bytes(metadata),
                overwrite=False,
                content_type='application/json',
            )
        except StorageConflictError as error:
            raise SourceCorruptionError('Generated source release id already exists') from error
        except StorageError as error:
            raise SourceUnavailableError('Could not materialize Blob source release') from error
        return metadata

    def _promote_manifest(
        self,
        *,
        source_key: SourceKey,
        payload: bytes,
        observed_etag: str | None,
    ) -> None:
        blob_name = self._manifest_blob_name(source_key)
        if observed_etag is None:
            self._storage.upload(
                container_name=self._settings.container_name,
                blob_name=blob_name,
                data=payload,
                overwrite=False,
                content_type='application/json',
            )
            return
        self._storage.upload_if_match(
            container_name=self._settings.container_name,
            blob_name=blob_name,
            data=payload,
            etag=observed_etag,
            content_type='application/json',
        )

    def _recover_ambiguous_promotion(
        self,
        *,
        request: PublishRequest,
        metadata: SourceReleaseMetadata,
        expected_snapshot: SourceSnapshot,
        candidate_snapshot: SourceSnapshot,
        error: StorageError,
    ) -> PublishResult:
        try:
            recovered = self._observe_current(request.source_key).snapshot
        except SourceUnavailableError as recovery_error:
            raise SourceUnavailableError(
                'Could not determine Blob source publication outcome'
            ) from recovery_error

        if recovered == candidate_snapshot:
            return PublishResult(release=metadata, snapshot=recovered)
        if recovered == expected_snapshot:
            raise SourceUnavailableError('Blob source publication was not promoted') from error
        raise SourceConcurrencyError(
            'Source changed while publication outcome was uncertain'
        ) from error

    def _read_release_metadata(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> SourceReleaseMetadata:
        try:
            payload = self._storage.download(
                container_name=self._settings.container_name,
                blob_name=self._release_metadata_blob_name(source_key, release_ref),
            )
        except StorageBlobNotFoundError as error:
            raise SourceReleaseNotFoundError(
                f'Source release not found: {release_ref.release_id.value}'
            ) from error
        except StorageError as error:
            raise SourceUnavailableError('Could not read Blob source release metadata') from error

        try:
            metadata = release_metadata_from_bytes(payload)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise SourceCorruptionError('Source release metadata is invalid') from error
        if metadata.source_key != source_key or metadata.release_ref != release_ref:
            raise SourceCorruptionError('Source release metadata does not match requested release')
        return metadata

    def _publication_time(self, previous_ref: SourceReleaseRef | None) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError('Blob source clock must return a timezone-aware datetime')
        current = current.astimezone(timezone.utc)
        if previous_ref is not None and current <= previous_ref.published_at_utc:
            return previous_ref.published_at_utc + timedelta(microseconds=1)
        return current

    def _source_prefix(self, source_key: SourceKey) -> str:
        return _join_blob_name(
            self._settings.root_prefix,
            'sources',
            encode_segment(source_key.value),
        )

    def _manifest_blob_name(self, source_key: SourceKey) -> str:
        return _join_blob_name(self._source_prefix(source_key), 'manifest.json')

    def _release_prefix(self, source_key: SourceKey, release_ref: SourceReleaseRef) -> str:
        published_at = release_ref.published_at_utc
        return _join_blob_name(
            self._source_prefix(source_key),
            'history',
            f'year={published_at.year:04d}',
            f'month={published_at.month:02d}',
            f'day={published_at.day:02d}',
            encode_segment(release_ref.release_id.value),
        )

    def _release_metadata_blob_name(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> str:
        return _join_blob_name(self._release_prefix(source_key, release_ref), 'release.json')

    def _resource_blob_name(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
        logical_path: str,
    ) -> str:
        return _join_blob_name(
            self._release_prefix(source_key, release_ref),
            'resources',
            logical_path,
        )


def _require_container_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError('Blob source container name must be text')
    normalized = value.strip()
    if not normalized:
        raise ValueError('Blob source container name must not be empty')
    return normalized


def _normalize_root_prefix(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError('Blob source root prefix must be text')
    normalized = value.strip()
    if not normalized:
        return ''
    if (
        normalized.startswith('/')
        or normalized.endswith('/')
        or '\\' in normalized
        or '\x00' in normalized
        or any(part in {'', '.', '..'} for part in normalized.split('/'))
    ):
        raise ValueError('Blob source root prefix must be a safe relative blob prefix')
    return normalized


def _join_blob_name(*parts: str) -> str:
    return '/'.join(part for part in parts if part)
