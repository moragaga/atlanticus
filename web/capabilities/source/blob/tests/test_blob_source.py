from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock

import pytest

from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageBlobProperties,
    StorageConflictError,
    StorageConnectionError,
)
from atlanticus.web.source._codec import SCHEMA_VERSION, manifest_to_bytes, token_for_manifest
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.source.errors import (
    SourceConcurrencyError,
    SourceCorruptionError,
    SourceReleaseNotFoundError,
    SourceUnavailableError,
)
from atlanticus.web.source.models import (
    HistoryQuery,
    PublishRequest,
    SourceKey,
    SourceManifest,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceResource,
)

_CONTAINER = 'source-data'
_SOURCE_KEY = SourceKey('tool-configuration')


class FakeStorage:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.etags: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self._sequence = 0
        self._lock = Lock()
        self.manifest_create_failure: str | None = None
        self.manifest_match_failure: str | None = None
        self.replacement_manifest: bytes | None = None

    def get_properties(self, *, container_name: str, blob_name: str) -> StorageBlobProperties:
        self._require_container(container_name)
        with self._lock:
            self.calls.append(('properties', blob_name))
            if blob_name not in self.blobs:
                raise StorageBlobNotFoundError('Storage blob not found')
            payload = self.blobs[blob_name]
            return StorageBlobProperties(
                name=blob_name,
                size=len(payload),
                etag=self.etags[blob_name],
            )

    def download(self, *, container_name: str, blob_name: str) -> bytes:
        self._require_container(container_name)
        with self._lock:
            self.calls.append(('download', blob_name))
            if blob_name not in self.blobs:
                raise StorageBlobNotFoundError('Storage blob not found')
            return self.blobs[blob_name]

    def upload(
        self,
        *,
        container_name: str,
        blob_name: str,
        data: bytes,
        overwrite: bool = True,
        metadata=None,
        content_type: str | None = None,
    ) -> None:
        del metadata, content_type
        self._require_container(container_name)
        payload = bytes(data)
        with self._lock:
            self.calls.append(('upload', blob_name))
            is_manifest = blob_name.endswith('/manifest.json')
            if is_manifest and self.manifest_create_failure == 'before':
                self.manifest_create_failure = None
                raise StorageConnectionError('Ambiguous create')
            if not overwrite and blob_name in self.blobs:
                raise StorageConflictError('Storage conflict')
            self._put(blob_name, payload)
            if is_manifest and self.manifest_create_failure == 'after':
                self.manifest_create_failure = None
                raise StorageConnectionError('Ambiguous create')

    def upload_if_match(
        self,
        *,
        container_name: str,
        blob_name: str,
        data: bytes,
        etag: str,
        metadata=None,
        content_type: str | None = None,
    ) -> None:
        del metadata, content_type
        self._require_container(container_name)
        payload = bytes(data)
        with self._lock:
            self.calls.append(('upload_if_match', blob_name))
            if blob_name not in self.blobs:
                raise StorageBlobNotFoundError('Storage blob not found')
            if self.etags[blob_name] != etag:
                raise StorageConflictError('Storage conflict')
            if self.manifest_match_failure == 'before':
                self.manifest_match_failure = None
                raise StorageConnectionError('Ambiguous conditional write')
            if self.manifest_match_failure == 'replace':
                replacement = self.replacement_manifest
                if replacement is None:
                    raise AssertionError('replacement_manifest must be configured')
                self.manifest_match_failure = None
                self._put(blob_name, replacement)
                raise StorageConnectionError('Ambiguous conditional write')
            self._put(blob_name, payload)
            if self.manifest_match_failure == 'after':
                self.manifest_match_failure = None
                raise StorageConnectionError('Ambiguous conditional write')

    def tamper(self, blob_name: str, payload: bytes) -> None:
        with self._lock:
            if blob_name not in self.blobs:
                raise KeyError(blob_name)
            self._put(blob_name, payload)

    def _put(self, blob_name: str, payload: bytes) -> None:
        self._sequence += 1
        self.blobs[blob_name] = payload
        self.etags[blob_name] = f'"etag-{self._sequence}"'

    @staticmethod
    def _require_container(container_name: str) -> None:
        assert container_name == _CONTAINER


def _store(
    storage: FakeStorage,
    *,
    times: Iterator[datetime] | None = None,
    release_ids: Iterator[SourceReleaseId] | None = None,
    root_prefix: str = '',
) -> BlobSourceStore:
    clock = (lambda: next(times)) if times is not None else None
    release_id_factory = (lambda: next(release_ids)) if release_ids is not None else None
    return BlobSourceStore(
        BlobSourceSettings(_CONTAINER, root_prefix),
        storage=storage,
        clock=clock,
        release_id_factory=release_id_factory,
    )


def _publish(
    store: BlobSourceStore,
    content: bytes,
    *,
    token=None,
    basis_release=None,
):
    return store.publish(
        PublishRequest(
            source_key=_SOURCE_KEY,
            resources=(SourceResource('definition.json', content),),
            expected_concurrency_token=token,
            basis_release=basis_release,
        )
    )


def _manifest_name(root_prefix: str = '') -> str:
    prefix = f'{root_prefix}/' if root_prefix else ''
    return f'{prefix}sources/dG9vbC1jb25maWd1cmF0aW9u/manifest.json'


def test_settings_reject_unsafe_root_prefix() -> None:
    assert BlobSourceSettings(_CONTAINER, 'atlanticus/source').root_prefix == 'atlanticus/source'
    with pytest.raises(ValueError):
        BlobSourceSettings(_CONTAINER, '/absolute')
    with pytest.raises(ValueError):
        BlobSourceSettings(_CONTAINER, 'source/../other')


def test_first_publish_is_restartable_and_uses_shared_blob_layout() -> None:
    storage = FakeStorage()
    instant = datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc)
    store = _store(
        storage,
        times=iter((instant,)),
        release_ids=iter((SourceReleaseId('release/1'),)),
        root_prefix='atlanticus/config',
    )

    result = _publish(store, b'{"value":1}')

    release_prefix = (
        'atlanticus/config/sources/dG9vbC1jb25maWd1cmF0aW9u/'
        'history/year=2026/month=09/day=12/cmVsZWFzZS8x'
    )
    manifest_name = _manifest_name('atlanticus/config')
    assert f'{release_prefix}/resources/definition.json' in storage.blobs
    assert f'{release_prefix}/release.json' in storage.blobs
    assert manifest_name in storage.blobs
    assert result.snapshot.concurrency_token == token_for_manifest(storage.blobs[manifest_name])
    assert result.snapshot.concurrency_token.value != storage.etags[manifest_name]

    restarted = _store(storage, root_prefix='atlanticus/config')
    storage.calls.clear()
    assert restarted.get_current(_SOURCE_KEY) == result.snapshot
    assert storage.calls[:2] == [
        ('properties', manifest_name),
        ('download', manifest_name),
    ]
    metadata, resources = restarted.read_release(_SOURCE_KEY, result.release.release_ref)
    assert metadata == result.release
    assert resources == (SourceResource('definition.json', b'{"value":1}'),)


def test_same_content_republish_creates_distinct_release_with_same_hash() -> None:
    storage = FakeStorage()
    store = _store(
        storage,
        release_ids=iter((SourceReleaseId('first'), SourceReleaseId('second'))),
    )
    first = _publish(store, b'same')
    second = _publish(
        store,
        b'same',
        token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )

    assert first.release.release_ref != second.release.release_ref
    assert first.release.content_hash == second.release.content_hash
    assert second.release.previous_published_release == first.release.release_ref
    assert second.release.basis_release == first.release.release_ref


def test_stale_snapshot_cannot_promote() -> None:
    storage = FakeStorage()
    store = _store(storage)
    first = _publish(store, b'one')
    stale = first.snapshot.concurrency_token
    second = _publish(store, b'two', token=stale)

    with pytest.raises(SourceConcurrencyError):
        _publish(store, b'three', token=stale)

    assert store.get_current(_SOURCE_KEY) == second.snapshot


def test_concurrent_first_publish_has_one_winner_and_history_excludes_orphan() -> None:
    storage = FakeStorage()
    barrier = Barrier(2)
    sequence_lock = Lock()
    release_ids = iter((SourceReleaseId('candidate-a'), SourceReleaseId('candidate-b')))

    def release_id_factory() -> SourceReleaseId:
        with sequence_lock:
            return next(release_ids)

    def clock() -> datetime:
        barrier.wait(timeout=5)
        return datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc)

    store = BlobSourceStore(
        BlobSourceSettings(_CONTAINER),
        storage=storage,
        clock=clock,
        release_id_factory=release_id_factory,
    )

    def publish(content: bytes):
        try:
            return _publish(store, content)
        except SourceConcurrencyError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, (b'a', b'b')))

    winners = [item for item in outcomes if not isinstance(item, Exception)]
    conflicts = [item for item in outcomes if isinstance(item, SourceConcurrencyError)]
    assert len(winners) == 1
    assert len(conflicts) == 1

    history = store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=10))
    assert len(history.items) == 1
    assert history.items[0].release_ref == winners[0].release.release_ref


def test_concurrent_update_has_one_conditional_winner_and_excludes_loser() -> None:
    storage = FakeStorage()
    initial = _store(storage, release_ids=iter((SourceReleaseId('initial'),)))
    first = _publish(initial, b'base')
    barrier = Barrier(2)
    sequence_lock = Lock()
    release_ids = iter((SourceReleaseId('candidate-a'), SourceReleaseId('candidate-b')))

    def release_id_factory() -> SourceReleaseId:
        with sequence_lock:
            return next(release_ids)

    def clock() -> datetime:
        barrier.wait(timeout=5)
        return first.release.release_ref.published_at_utc + timedelta(minutes=1)

    store = BlobSourceStore(
        BlobSourceSettings(_CONTAINER),
        storage=storage,
        clock=clock,
        release_id_factory=release_id_factory,
    )

    def publish(content: bytes):
        try:
            return _publish(store, content, token=first.snapshot.concurrency_token)
        except SourceConcurrencyError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, (b'a', b'b')))

    winners = [item for item in outcomes if not isinstance(item, Exception)]
    conflicts = [item for item in outcomes if isinstance(item, SourceConcurrencyError)]
    assert len(winners) == 1
    assert len(conflicts) == 1

    history = store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=10))
    assert [item.release_ref for item in history.items] == [
        winners[0].release.release_ref,
        first.release.release_ref,
    ]


def test_history_follows_predecessor_chain_with_stable_pagination() -> None:
    storage = FakeStorage()
    base = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    store = _store(storage, times=iter(base + timedelta(minutes=index) for index in range(4)))
    first = _publish(store, b'1')
    second = _publish(store, b'2', token=first.snapshot.concurrency_token)
    third = _publish(store, b'3', token=second.snapshot.concurrency_token)

    first_page = store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=2))
    assert [item.release_ref for item in first_page.items] == [
        third.release.release_ref,
        second.release.release_ref,
    ]
    assert first_page.next_cursor is not None

    fourth = _publish(store, b'4', token=third.snapshot.concurrency_token)
    second_page = store.query_history(
        HistoryQuery(source_key=_SOURCE_KEY, page_size=2, cursor=first_page.next_cursor)
    )
    assert [item.release_ref for item in second_page.items] == [first.release.release_ref]
    assert fourth.release.release_ref not in [item.release_ref for item in second_page.items]


def test_integrity_reports_missing_resource_and_read_rejects_corruption() -> None:
    storage = FakeStorage()
    store = _store(storage)
    result = _publish(store, b'payload')
    resource_name = next(
        name for name in storage.blobs if name.endswith('/resources/definition.json')
    )
    del storage.blobs[resource_name]
    del storage.etags[resource_name]

    integrity = store.verify_release(_SOURCE_KEY, result.release.release_ref)
    assert integrity.valid is False
    assert [failure.code for failure in integrity.failures] == ['missing_resource']
    with pytest.raises(SourceCorruptionError):
        store.read_release(_SOURCE_KEY, result.release.release_ref)


def test_tampered_resource_reports_digest_and_content_hash_failures() -> None:
    storage = FakeStorage()
    store = _store(storage)
    result = _publish(store, b'payload')
    resource_name = next(
        name for name in storage.blobs if name.endswith('/resources/definition.json')
    )
    storage.tamper(resource_name, b'PAYLOAD')

    integrity = store.verify_release(_SOURCE_KEY, result.release.release_ref)
    assert integrity.valid is False
    assert {'digest_mismatch', 'content_hash_mismatch'} <= {
        failure.code for failure in integrity.failures
    }


def test_missing_release_is_not_found() -> None:
    storage = FakeStorage()
    store = _store(storage)
    missing = SourceReleaseRef(
        SourceReleaseId('missing'),
        datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(SourceReleaseNotFoundError):
        store.verify_release(_SOURCE_KEY, missing)


def test_ambiguous_ack_after_first_manifest_create_recovers_success() -> None:
    storage = FakeStorage()
    storage.manifest_create_failure = 'after'
    store = _store(storage)

    result = _publish(store, b'payload')

    assert store.get_current(_SOURCE_KEY) == result.snapshot
    assert len(store.query_history(HistoryQuery(source_key=_SOURCE_KEY)).items) == 1


def test_ambiguous_ack_before_first_manifest_create_is_not_retried() -> None:
    storage = FakeStorage()
    storage.manifest_create_failure = 'before'
    store = _store(storage)

    with pytest.raises(SourceUnavailableError):
        _publish(store, b'payload')

    assert store.get_current(_SOURCE_KEY).current is None
    assert len(store.query_history(HistoryQuery(source_key=_SOURCE_KEY)).items) == 0
    manifest_uploads = sum(
        operation == 'upload' and name.endswith('/manifest.json')
        for operation, name in storage.calls
    )
    assert manifest_uploads == 1


def test_ambiguous_ack_after_conditional_write_recovers_success() -> None:
    storage = FakeStorage()
    store = _store(storage)
    first = _publish(store, b'one')
    storage.manifest_match_failure = 'after'

    second = _publish(store, b'two', token=first.snapshot.concurrency_token)

    assert store.get_current(_SOURCE_KEY) == second.snapshot


def test_ambiguous_ack_with_different_current_becomes_concurrency_conflict() -> None:
    storage = FakeStorage()
    store = _store(storage)
    first = _publish(store, b'one')
    competitor_ref = SourceReleaseRef(
        SourceReleaseId('competitor'),
        first.release.release_ref.published_at_utc + timedelta(minutes=1),
    )
    competitor = SourceManifest(
        schema_version=SCHEMA_VERSION,
        source_key=_SOURCE_KEY,
        current=SourceReleaseSummary(competitor_ref, first.release.content_hash),
    )
    storage.replacement_manifest = manifest_to_bytes(competitor)
    storage.manifest_match_failure = 'replace'

    with pytest.raises(SourceConcurrencyError):
        _publish(store, b'two', token=first.snapshot.concurrency_token)

    assert store.get_current(_SOURCE_KEY).current == competitor.current
