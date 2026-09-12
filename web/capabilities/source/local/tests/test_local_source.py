from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Lock

import pytest

from atlanticus.web.source.errors import (
    SourceConcurrencyError,
    SourceCorruptionError,
    SourceInvalidCursorError,
)
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import (
    HistoryQuery,
    PublishRequest,
    SourceKey,
    SourceReleaseId,
    SourceResource,
)


def _store(root: Path, times: Iterator[datetime] | None = None) -> LocalSourceStore:
    clock = (lambda: next(times)) if times is not None else None
    return LocalSourceStore(LocalSourceSettings(root), clock=clock)


def _publish(
    store: LocalSourceStore,
    source_key: SourceKey,
    content: bytes,
    *,
    token=None,
    basis_release=None,
):
    return store.publish(
        PublishRequest(
            source_key=source_key,
            resources=(SourceResource('definition.json', content),),
            expected_concurrency_token=token,
            basis_release=basis_release,
        )
    )


def test_first_publish_is_durable_and_restartable(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    store = _store(tmp_path)

    result = _publish(store, source_key, b'{"value":1}')

    assert result.snapshot.current is not None
    assert result.snapshot.concurrency_token is not None
    restarted = _store(tmp_path)
    snapshot = restarted.get_current(source_key)
    assert snapshot == result.snapshot
    metadata, resources = restarted.read_release(source_key, result.release.release_ref)
    assert metadata == result.release
    assert resources[0].content == b'{"value":1}'


def test_republish_same_content_creates_distinct_release_with_same_hash(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    store = _store(tmp_path)

    first = _publish(store, source_key, b'same')
    second = _publish(
        store,
        source_key,
        b'same',
        token=first.snapshot.concurrency_token,
        basis_release=first.release.release_ref,
    )

    assert first.release.release_ref != second.release.release_ref
    assert first.release.content_hash == second.release.content_hash
    assert second.release.previous_published_release == first.release.release_ref
    assert second.release.basis_release == first.release.release_ref


def test_stale_snapshot_cannot_promote(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    store = _store(tmp_path)
    first = _publish(store, source_key, b'one')
    stale = first.snapshot.concurrency_token
    second = _publish(store, source_key, b'two', token=stale)

    with pytest.raises(SourceConcurrencyError):
        _publish(store, source_key, b'three', token=stale)

    assert store.get_current(source_key) == second.snapshot


def test_concurrent_first_publish_has_one_winner_and_history_excludes_orphan(
    tmp_path: Path,
) -> None:
    source_key = SourceKey('tool-configuration')
    barrier = Barrier(2)
    sequence_lock = Lock()
    release_ids = iter((SourceReleaseId('candidate-a'), SourceReleaseId('candidate-b')))

    def release_id_factory() -> SourceReleaseId:
        with sequence_lock:
            return next(release_ids)

    def clock() -> datetime:
        barrier.wait(timeout=5)
        return datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    store = LocalSourceStore(
        LocalSourceSettings(tmp_path),
        clock=clock,
        release_id_factory=release_id_factory,
    )

    def publish(content: bytes):
        try:
            return _publish(store, source_key, content)
        except SourceConcurrencyError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, (b'a', b'b')))

    winners = [item for item in outcomes if not isinstance(item, Exception)]
    conflicts = [item for item in outcomes if isinstance(item, SourceConcurrencyError)]
    assert len(winners) == 1
    assert len(conflicts) == 1

    history = store.query_history(HistoryQuery(source_key=source_key, page_size=10))
    assert len(history.items) == 1
    assert history.items[0].release_ref == winners[0].release.release_ref


def test_history_follows_publication_chain_with_stable_pagination(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    base = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    times = iter(base + timedelta(minutes=index) for index in range(4))
    store = _store(tmp_path, times)

    first = _publish(store, source_key, b'1')
    second = _publish(store, source_key, b'2', token=first.snapshot.concurrency_token)
    third = _publish(store, source_key, b'3', token=second.snapshot.concurrency_token)

    first_page = store.query_history(HistoryQuery(source_key=source_key, page_size=2))
    assert [item.release_ref for item in first_page.items] == [
        third.release.release_ref,
        second.release.release_ref,
    ]
    assert first_page.next_cursor is not None

    fourth = _publish(store, source_key, b'4', token=third.snapshot.concurrency_token)
    second_page = store.query_history(
        HistoryQuery(source_key=source_key, page_size=2, cursor=first_page.next_cursor)
    )
    assert [item.release_ref for item in second_page.items] == [first.release.release_ref]
    assert fourth.release.release_ref not in [item.release_ref for item in second_page.items]


def test_history_date_filter_is_inclusive(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    base = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    times = iter(base + timedelta(hours=index) for index in range(3))
    store = _store(tmp_path, times)

    first = _publish(store, source_key, b'1')
    second = _publish(store, source_key, b'2', token=first.snapshot.concurrency_token)
    third = _publish(store, source_key, b'3', token=second.snapshot.concurrency_token)

    page = store.query_history(
        HistoryQuery(
            source_key=source_key,
            published_from_utc=second.release.release_ref.published_at_utc,
            published_to_utc=third.release.release_ref.published_at_utc,
            page_size=10,
        )
    )
    assert [item.release_ref for item in page.items] == [
        third.release.release_ref,
        second.release.release_ref,
    ]


def test_invalid_or_cross_source_cursor_is_rejected(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    store = _store(tmp_path)
    first = _publish(store, source_key, b'1')
    second = _publish(store, source_key, b'2', token=first.snapshot.concurrency_token)
    page = store.query_history(HistoryQuery(source_key=source_key, page_size=1))
    assert page.next_cursor is not None

    with pytest.raises(SourceInvalidCursorError):
        store.query_history(
            HistoryQuery(
                source_key=SourceKey('other-source'),
                page_size=1,
                cursor=page.next_cursor,
            )
        )
    assert second.release.previous_published_release == first.release.release_ref


def test_verify_release_reports_missing_resource_without_changing_current(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    store = _store(tmp_path)
    result = _publish(store, source_key, b'payload')
    snapshot = store.get_current(source_key)

    encoded_key = next((tmp_path / 'sources').iterdir())
    release_directory = next(encoded_key.glob('history/year=*/month=*/day=*/*'))
    (release_directory / 'resources' / 'definition.json').unlink()

    integrity = store.verify_release(source_key, result.release.release_ref)
    assert integrity.valid is False
    assert [failure.code for failure in integrity.failures] == ['missing_resource']
    assert store.get_current(source_key) == snapshot


def test_tampered_resource_fails_integrity_and_read(tmp_path: Path) -> None:
    source_key = SourceKey('tool-configuration')
    store = _store(tmp_path)
    result = _publish(store, source_key, b'payload')

    encoded_key = next((tmp_path / 'sources').iterdir())
    release_directory = next(encoded_key.glob('history/year=*/month=*/day=*/*'))
    (release_directory / 'resources' / 'definition.json').write_bytes(b'PAYLOAD')

    integrity = store.verify_release(source_key, result.release.release_ref)
    assert integrity.valid is False
    assert 'digest_mismatch' in {failure.code for failure in integrity.failures}
    assert 'content_hash_mismatch' in {failure.code for failure in integrity.failures}
    with pytest.raises(SourceCorruptionError):
        store.read_release(source_key, result.release.release_ref)


def test_cross_process_first_publish_promotes_exactly_one_candidate(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        import sys
        import time
        from datetime import datetime, timezone
        from pathlib import Path

        from atlanticus.web.source.errors import SourceConcurrencyError
        from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
        from atlanticus.web.source.models import PublishRequest, SourceKey, SourceResource

        root = Path(sys.argv[1])
        marker = root / f'barrier-{sys.argv[2]}'
        content = sys.argv[3].encode('utf-8')

        def clock():
            marker.write_text('ready', encoding='utf-8')
            deadline = time.monotonic() + 10
            while len(list(root.glob('barrier-*'))) < 2:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Cross-process test barrier timed out')
                time.sleep(0.01)
            return datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)

        store = LocalSourceStore(LocalSourceSettings(root), clock=clock)
        try:
            result = store.publish(
                PublishRequest(
                    source_key=SourceKey('tool-configuration'),
                    resources=(SourceResource('definition.json', content),),
                    expected_concurrency_token=None,
                )
            )
            print(f'published:{result.release.release_ref.release_id.value}')
        except SourceConcurrencyError:
            print('conflict')
        """
    )
    processes = [
        subprocess.Popen(
            [sys.executable, '-c', script, str(tmp_path), str(index), content],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index, content in enumerate(('process-a', 'process-b'))
    ]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        outputs.append(stdout.strip())

    assert sum(item == 'conflict' for item in outputs) == 1
    published = [item.removeprefix('published:') for item in outputs if item.startswith('published:')]
    assert len(published) == 1

    store = _store(tmp_path)
    history = store.query_history(HistoryQuery(source_key=SourceKey('tool-configuration')))
    assert len(history.items) == 1
    assert history.items[0].release_ref.release_id.value == published[0]
