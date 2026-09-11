from __future__ import annotations

from pathlib import Path

from atlanticus.web.bootstrap import (
    BOOTSTRAP_FOUNDATION_ASSET_LAYER,
    create_bootstrap_foundation_web_module,
)

_ROOT = Path(__file__).resolve().parents[1]
_FOUNDATION = _ROOT / 'src/atlanticus/web/bootstrap/resources/foundation'


def test_bootstrap_foundation_is_explicit_asset_only_module() -> None:
    module = create_bootstrap_foundation_web_module()

    assert module.name == 'bootstrap-foundation'
    assert module.asset_layers == (BOOTSTRAP_FOUNDATION_ASSET_LAYER,)
    assert BOOTSTRAP_FOUNDATION_ASSET_LAYER.load_order == 30
    assert BOOTSTRAP_FOUNDATION_ASSET_LAYER.package == 'atlanticus.web.bootstrap'
    assert BOOTSTRAP_FOUNDATION_ASSET_LAYER.resource_directory == 'resources/foundation'
    assert module.register_services is None
    assert module.register_callbacks is None


def test_bootstrap_foundation_manifest_resolves_local_css_and_fonts() -> None:
    entries = (_FOUNDATION / 'css/css.list').read_text(encoding='utf-8').splitlines()

    assert entries == ['00-bootstrap.min.css', '10-bootstrap-icons.min.css']
    assert all((_FOUNDATION / 'css' / entry).is_file() for entry in entries)
    assert (_FOUNDATION / 'fonts/bootstrap-icons.woff2').is_file()
    assert (_FOUNDATION / 'fonts/bootstrap-icons.woff').is_file()
    assert not (_FOUNDATION / 'js').exists()
