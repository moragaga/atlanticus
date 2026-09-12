from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from time import monotonic, sleep

import pytest
from azure.storage.blob import BlobServiceClient

from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConnectionError,
    StorageConnectionStringCredential,
    StorageSettings,
)
from atlanticus.web.source._codec import encode_segment
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.source.errors import SourceConcurrencyError, SourceCorruptionError
from atlanticus.web.source.models import (
    HistoryQuery,
    PublishRequest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceResource,
)

_CONTAINER = 'atlanticus-source-blob-integration'
_SOURCE_KEY = SourceKey('tool-configuration')


def _require_integration() -> None:
    if os.getenv('ATLANTICUS_RUN_SOURCE_BLOB_INTEGRATION') != '1':
        pytest.skip('Source Blob integration is disabled')


def _connection_string() -> str:
    return os.environ['ATLANTICUS_STORAGE_CONNECTION_STRING']


def _wait_until_ready() -> BlobServiceClient:
    deadline = monotonic() + 30
    last_error: BaseException | None = None
    while monotonic() < deadline:
        service = BlobServiceClient.from_connection_string(_connection_string())
        try:
            next(iter(service.list_containers()), None)
            return service
        except Exception as error:
            last_error = error
            service.close()
            sleep(0.5)
    raise RuntimeError('Azurite did not become ready') from last_error


@pytest.fixture(scope='module')
def blob_service() -> Iterator[BlobServiceClient]:
    _require_integration()
    service = _wait_until_ready()
    container = service.get_container_client(_CONTAINER)
    try:
        container.create_container()
    except Exception as error:
        if getattr(error, 'status_code', None) != 409:
            raise
    try:
        yield service
    finally:
        try:
            container.delete_container()
        finally:
            service.close()


def _connection_client() -> StorageClient:
    return StorageClient(
        settings=StorageSettings(
            credential=StorageConnectionStringCredential(connection_string=_connection_string())
        )
    )


def _store(
    storage: object,
    *,
    root_prefix: str,
    release_id: str | None = None,
    clock=None,
) -> BlobSourceStore:
    release_id_factory = (lambda: SourceReleaseId(release_id)) if release_id is not None else None
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


def _source_history_prefix(root_prefix: str) -> str:
    return f'{root_prefix}/sources/{encode_segment(_SOURCE_KEY.value)}/history/'


def _release_prefix(root_prefix: str, release_ref: SourceReleaseRef) -> str:
    published_at = release_ref.published_at_utc
    return (
        f'{_source_history_prefix(root_prefix)}'
        f'year={published_at.year:04d}/'
        f'month={published_at.month:02d}/'
        f'day={published_at.day:02d}/'
        f'{encode_segment(release_ref.release_id.value)}'
    )


def _release_metadata_names(service: BlobServiceClient, root_prefix: str) -> tuple[str, ...]:
    container = service.get_container_client(_CONTAINER)
    return tuple(
        item.name
        for item in container.list_blobs(name_starts_with=_source_history_prefix(root_prefix))
        if item.name.endswith('/release.json')
    )


class _AmbiguousAfterManifestWrite:
    def __init__(self, storage: StorageClient, *, conditional: bool) -> None:
        self._storage = storage
        self._conditional = conditional
        self._raised = False

    def get_properties(self, **kwargs):
        return self._storage.get_properties(**kwargs)

    def download(self, **kwargs):
        return self._storage.download(**kwargs)

    def upload(self, **kwargs) -> None:
        self._storage.upload(**kwargs)
        blob_name = kwargs['blob_name']
        overwrite = kwargs.get('overwrite', True)
        if (
            not self._conditional
            and not self._raised
            and not overwrite
            and blob_name.endswith('/manifest.json')
        ):
            self._raised = True
            raise StorageConnectionError('Simulated lost ACK after manifest create')

    def upload_if_match(self, **kwargs) -> None:
        self._storage.upload_if_match(**kwargs)
        blob_name = kwargs['blob_name']
        if self._conditional and not self._raised and blob_name.endswith('/manifest.json'):
            self._raised = True
            raise StorageConnectionError('Simulated lost ACK after conditional manifest write')


def test_first_publish_is_restartable_and_readable_from_azurite(
    blob_service: BlobServiceClient,
) -> None:
    del blob_service
    root_prefix = 'integration/first-publish'
    published_at = datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc)

    with _connection_client() as client:
        store = _store(
            client,
            root_prefix=root_prefix,
            release_id='first-release',
            clock=lambda: published_at,
        )
        result = _publish(store, b'{"value":1}')

    with _connection_client() as client:
        restarted = _store(client, root_prefix=root_prefix)
        assert restarted.get_current(_SOURCE_KEY) == result.snapshot
        metadata, resources = restarted.read_release(_SOURCE_KEY, result.release.release_ref)
        assert metadata == result.release
        assert resources == (SourceResource('definition.json', b'{"value":1}'),)
        integrity = restarted.verify_release(_SOURCE_KEY, result.release.release_ref)
        assert integrity.valid is True
        assert integrity.checked_resources == 1


def test_stale_token_cannot_promote_against_real_etag(blob_service: BlobServiceClient) -> None:
    del blob_service
    root_prefix = 'integration/stale-token'

    with _connection_client() as client:
        store = _store(client, root_prefix=root_prefix)
        first = _publish(store, b'one')
        stale = first.snapshot.concurrency_token
        second = _publish(store, b'two', token=stale)

        with pytest.raises(SourceConcurrencyError):
            _publish(store, b'three', token=stale)

        assert store.get_current(_SOURCE_KEY) == second.snapshot


def test_concurrent_first_publish_has_one_winner_and_orphan_is_not_history(
    blob_service: BlobServiceClient,
) -> None:
    root_prefix = 'integration/concurrent-first'
    barrier = Barrier(2)
    published_at = datetime(2026, 9, 12, 16, 10, tzinfo=timezone.utc)

    def publish(release_id: str, content: bytes):
        with _connection_client() as client:
            store = _store(
                client,
                root_prefix=root_prefix,
                release_id=release_id,
                clock=lambda: (barrier.wait(timeout=10), published_at)[1],
            )
            try:
                return _publish(store, content)
            except SourceConcurrencyError as error:
                return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: publish(*args),
                (('candidate-a', b'a'), ('candidate-b', b'b')),
            )
        )

    winners = [item for item in outcomes if not isinstance(item, Exception)]
    conflicts = [item for item in outcomes if isinstance(item, SourceConcurrencyError)]
    assert len(winners) == 1
    assert len(conflicts) == 1

    with _connection_client() as client:
        store = _store(client, root_prefix=root_prefix)
        history = store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=10))

    assert [item.release_ref for item in history.items] == [winners[0].release.release_ref]
    assert len(_release_metadata_names(blob_service, root_prefix)) == 2


def test_concurrent_update_has_one_etag_winner_and_loser_stays_out_of_history(
    blob_service: BlobServiceClient,
) -> None:
    root_prefix = 'integration/concurrent-update'
    base_time = datetime(2026, 9, 12, 16, 20, tzinfo=timezone.utc)

    with _connection_client() as client:
        initial_store = _store(
            client,
            root_prefix=root_prefix,
            release_id='initial',
            clock=lambda: base_time,
        )
        initial = _publish(initial_store, b'base')

    barrier = Barrier(2)
    update_time = base_time + timedelta(minutes=1)

    def publish(release_id: str, content: bytes):
        with _connection_client() as client:
            store = _store(
                client,
                root_prefix=root_prefix,
                release_id=release_id,
                clock=lambda: (barrier.wait(timeout=10), update_time)[1],
            )
            try:
                return _publish(
                    store,
                    content,
                    token=initial.snapshot.concurrency_token,
                )
            except SourceConcurrencyError as error:
                return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: publish(*args),
                (('candidate-a', b'a'), ('candidate-b', b'b')),
            )
        )

    winners = [item for item in outcomes if not isinstance(item, Exception)]
    conflicts = [item for item in outcomes if isinstance(item, SourceConcurrencyError)]
    assert len(winners) == 1
    assert len(conflicts) == 1

    with _connection_client() as client:
        store = _store(client, root_prefix=root_prefix)
        history = store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=10))

    assert [item.release_ref for item in history.items] == [
        winners[0].release.release_ref,
        initial.release.release_ref,
    ]
    assert len(_release_metadata_names(blob_service, root_prefix)) == 3


def test_integrity_detects_real_blob_tampering(blob_service: BlobServiceClient) -> None:
    root_prefix = 'integration/integrity'
    published_at = datetime(2026, 9, 12, 16, 30, tzinfo=timezone.utc)

    with _connection_client() as client:
        store = _store(
            client,
            root_prefix=root_prefix,
            release_id='tamper-release',
            clock=lambda: published_at,
        )
        result = _publish(store, b'payload')

        resource_name = (
            f'{_release_prefix(root_prefix, result.release.release_ref)}/resources/definition.json'
        )
        blob_service.get_blob_client(_CONTAINER, resource_name).upload_blob(
            b'PAYLOAD',
            overwrite=True,
        )

        integrity = store.verify_release(_SOURCE_KEY, result.release.release_ref)
        assert integrity.valid is False
        assert {'digest_mismatch', 'content_hash_mismatch'} <= {
            failure.code for failure in integrity.failures
        }
        with pytest.raises(SourceCorruptionError):
            store.read_release(_SOURCE_KEY, result.release.release_ref)


def test_lost_ack_after_real_first_manifest_write_recovers_success(
    blob_service: BlobServiceClient,
) -> None:
    del blob_service
    root_prefix = 'integration/ambiguous-first'

    with _connection_client() as client:
        storage = _AmbiguousAfterManifestWrite(client, conditional=False)
        store = _store(storage, root_prefix=root_prefix, release_id='ambiguous-first')
        result = _publish(store, b'payload')

        assert store.get_current(_SOURCE_KEY) == result.snapshot
        history = store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=10))
        assert [item.release_ref for item in history.items] == [result.release.release_ref]


def test_lost_ack_after_real_conditional_write_recovers_success(
    blob_service: BlobServiceClient,
) -> None:
    del blob_service
    root_prefix = 'integration/ambiguous-update'

    with _connection_client() as client:
        initial_store = _store(client, root_prefix=root_prefix, release_id='initial')
        initial = _publish(initial_store, b'base')

        storage = _AmbiguousAfterManifestWrite(client, conditional=True)
        update_store = _store(storage, root_prefix=root_prefix, release_id='updated')
        updated = _publish(
            update_store,
            b'updated',
            token=initial.snapshot.concurrency_token,
        )

        assert update_store.get_current(_SOURCE_KEY) == updated.snapshot
        history = update_store.query_history(HistoryQuery(source_key=_SOURCE_KEY, page_size=10))
        assert [item.release_ref for item in history.items] == [
            updated.release.release_ref,
            initial.release.release_ref,
        ]
