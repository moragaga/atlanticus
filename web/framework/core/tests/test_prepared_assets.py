from __future__ import annotations

import json
from pathlib import Path

import pytest

import atlanticus.web.assets as assets_module
from atlanticus.web.assets import AssetLayer, resolve_asset_publication
from atlanticus.web.errors import WebAssetError


def _layer(tmp_path: Path) -> AssetLayer:
    resources = tmp_path / 'local' / 'resources'
    (resources / 'css').mkdir(parents=True)
    (resources / 'js').mkdir()
    (resources / 'css' / '10-style.css').write_text(
        '.a { color: blue; }', encoding='utf-8',
    )
    (resources / 'css' / 'css.list').write_text('10-style.css\n', encoding='utf-8')
    (resources / 'js' / '10-script.js').write_text(
        'const value = 1;\n', encoding='utf-8',
    )
    (resources / 'js' / 'js.list').write_text('10-script.js\n', encoding='utf-8')
    return AssetLayer(name='local', load_order=200, source_directory=tmp_path / 'local')


def test_prepared_publication_is_reused_without_republishing(tmp_path, monkeypatch):
    layer = _layer(tmp_path)
    original = assets_module.publish_asset_layers
    calls = []

    def record(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(assets_module, 'publish_asset_layers', record)
    first = resolve_asset_publication(
        layers=(layer,), publications_root=tmp_path / 'published', optimize=True,
    )
    second = resolve_asset_publication(
        layers=(layer,), publications_root=tmp_path / 'published', optimize=True,
    )

    assert len(calls) == 1
    assert first == second
    assert first.css_entries == ('app.min.css',)
    manifest = json.loads(first.manifest_path.read_text(encoding='utf-8'))
    assert manifest['optimized'] is True


def test_source_change_and_optimization_mode_invalidate_prepared_identity(tmp_path):
    layer = _layer(tmp_path)
    root = tmp_path / 'published'
    plain = resolve_asset_publication(layers=(layer,), publications_root=root)
    optimized = resolve_asset_publication(
        layers=(layer,), publications_root=root, optimize=True,
    )
    assert plain.revision != optimized.revision
    css = tmp_path / 'local/resources/css/10-style.css'
    css.write_text('.a { color: red; }', encoding='utf-8')
    refreshed = resolve_asset_publication(
        layers=(layer,), publications_root=root, optimize=True,
    )
    assert refreshed.revision != optimized.revision


def test_corrupt_prepared_publication_fails_without_rebuilding(tmp_path, monkeypatch):
    layer = _layer(tmp_path)
    root = tmp_path / 'published'
    published = resolve_asset_publication(
        layers=(layer,), publications_root=root, optimize=True,
    )
    (published.assets_root / 'app.min.css').write_text('corrupt', encoding='utf-8')
    monkeypatch.setattr(
        assets_module,
        'publish_asset_layers',
        lambda **_kwargs: pytest.fail('Damaged prepared assets must not be regenerated'),
    )
    with pytest.raises(WebAssetError, match='integrity validation failed'):
        resolve_asset_publication(layers=(layer,), publications_root=root, optimize=True)

def test_parallel_first_publication_minifies_only_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from time import sleep

    layer = _layer(tmp_path)
    original = assets_module.publish_asset_layers
    start = Barrier(4)
    counter_lock = Lock()
    calls = 0

    def track(**kwargs):
        nonlocal calls
        with counter_lock:
            calls += 1
        sleep(0.1)
        return original(**kwargs)

    def prepare(_index):
        start.wait(timeout=5)
        return resolve_asset_publication(
            layers=(layer,), publications_root=tmp_path / 'shared', optimize=True,
        )

    monkeypatch.setattr(assets_module, 'publish_asset_layers', track)
    with ThreadPoolExecutor(max_workers=4) as pool:
        published = tuple(pool.map(prepare, range(4)))

    assert calls == 1
    assert len({item.revision for item in published}) == 1
    assert all(item.css_entries == ('app.min.css',) for item in published)


def test_separate_workers_prepare_one_shared_publication(tmp_path):
    import subprocess
    import sys
    from textwrap import dedent

    _layer(tmp_path)
    script = dedent("""
        import os
        import sys
        import time
        from pathlib import Path
        from atlanticus.web.assets import AssetLayer, resolve_asset_publication
        import atlanticus.web.assets as assets

        source, shared, ready, calls = map(Path, sys.argv[1:])
        ready.mkdir(parents=True, exist_ok=True)
        (ready / str(os.getpid())).write_text('ready', encoding='utf-8')
        deadline = time.monotonic() + 10
        while len(tuple(ready.iterdir())) < 4:
            if time.monotonic() > deadline:
                raise TimeoutError('Worker startup barrier was not reached')
            time.sleep(0.02)

        original = assets.publish_asset_layers
        def observed(**kwargs):
            with calls.open('a', encoding='utf-8') as record:
                record.write('build\\n')
            time.sleep(0.1)
            return original(**kwargs)

        assets.publish_asset_layers = observed
        layer = AssetLayer(name='local', load_order=200, source_directory=source)
        publication = resolve_asset_publication(
            layers=(layer,), publications_root=shared, optimize=True,
        )
        assert publication.css_entries == ('app.min.css',)
    """)
    processes = []
    try:
        for _ in range(4):
            processes.append(subprocess.Popen(
                [
                    sys.executable, '-c', script,
                    str(tmp_path / 'local'), str(tmp_path / 'shared'),
                    str(tmp_path / 'ready'), str(tmp_path / 'compilations.txt'),
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, f'{stdout}\n{stderr}'
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()

    assert (tmp_path / 'compilations.txt').read_text(encoding='utf-8').splitlines() == [
        'build',
    ]
