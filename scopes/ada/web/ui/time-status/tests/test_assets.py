from importlib.resources import files
from importlib.resources.abc import Traversable

_PACKAGE = 'ada.web.ui.time_status'


def _asset_entries(kind: str) -> tuple[Traversable, tuple[str, ...]]:
    root = files(_PACKAGE).joinpath(f'resources/{kind}')
    entries = tuple(root.joinpath(f'{kind}.list').read_text(encoding='utf-8').splitlines())
    return root, entries


def _packaged_asset_names(root: Traversable, suffix: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            entry.name
            for entry in root.iterdir()
            if entry.is_file() and entry.name.endswith(suffix)
        )
    )


def test_time_status_css_manifest_references_packaged_css() -> None:
    root, entries = _asset_entries('css')

    assert entries == ('10-time-status.css',)
    assert _packaged_asset_names(root, '.css') == tuple(sorted(entries))
    assert all(root.joinpath(entry).is_file() for entry in entries)


def test_time_status_js_manifest_references_packaged_js_in_load_order() -> None:
    root, entries = _asset_entries('js')

    assert entries == ('10-time-status-clock.js', '20-time-status-detail.js')
    assert _packaged_asset_names(root, '.js') == tuple(sorted(entries))
    assert all(root.joinpath(entry).is_file() for entry in entries)
