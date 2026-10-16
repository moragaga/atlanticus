from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import atlanticus.json.store as store_module
from atlanticus.json import JsonDocumentStore, JsonWriteError, JsonWriteOnceStatus


def test_windows_does_not_attempt_directory_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_open(*args: object, **kwargs: object) -> int:
        raise AssertionError('Windows directory must not be opened for fsync')

    monkeypatch.setattr(store_module, 'os', SimpleNamespace(name='nt', open=unexpected_open))

    store_module._fsync_directory(tmp_path)


def test_posix_fsyncs_directory_and_closes_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []

    def open_directory(path: Path, flags: int) -> int:
        calls.append(('open', path, flags))
        return 17

    def sync_descriptor(descriptor: int) -> None:
        calls.append(('fsync', descriptor))

    def close_descriptor(descriptor: int) -> None:
        calls.append(('close', descriptor))

    monkeypatch.setattr(
        store_module,
        'os',
        SimpleNamespace(
            name='posix',
            O_RDONLY=0,
            open=open_directory,
            fsync=sync_descriptor,
            close=close_descriptor,
        ),
    )

    store_module._fsync_directory(tmp_path)

    assert calls == [('open', tmp_path, 0), ('fsync', 17), ('close', 17)]


def test_posix_fsync_failure_still_closes_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[int] = []

    def sync_descriptor(_descriptor: int) -> None:
        raise OSError('simulated directory sync failure')

    monkeypatch.setattr(
        store_module,
        'os',
        SimpleNamespace(
            name='posix',
            O_RDONLY=0,
            open=lambda _path, _flags: 23,
            fsync=sync_descriptor,
            close=closed.append,
        ),
    )

    with pytest.raises(OSError, match='simulated directory sync failure'):
        store_module._fsync_directory(tmp_path)

    assert closed == [23]


def test_directory_sync_runs_after_new_json_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = JsonDocumentStore()
    path = tmp_path / 'latest.json'
    published: list[dict[str, int] | None] = []

    def observe_published_document(_directory: Path) -> None:
        published.append(store.read(path))

    monkeypatch.setattr(store_module, '_fsync_directory', observe_published_document)

    store.replace(path, {'revision': 2})

    assert published == [{'revision': 2}]
    assert store.read(path) == {'revision': 2}


def test_write_once_postpublication_sync_error_retains_visible_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = JsonDocumentStore()
    path = tmp_path / 'evaluation.json'

    def fail_sync(_directory: Path) -> None:
        raise OSError('simulated directory sync failure')

    monkeypatch.setattr(store_module, '_fsync_directory', fail_sync)

    with pytest.raises(JsonWriteError, match='could not write JSON document'):
        store.write_once(path, {'watermark': 10})

    assert store.read(path) == {'watermark': 10}
    assert store.write_once(path, {'watermark': 10}) is JsonWriteOnceStatus.UNCHANGED
    assert list(tmp_path.glob(f'.{path.name}.*.tmp')) == []
