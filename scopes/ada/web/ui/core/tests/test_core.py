from __future__ import annotations

import ast
from pathlib import Path

from ada.web.ui.core import ADA_UI_ASSET_LAYER, create_ada_ui_module

_ROOT = Path(__file__).resolve().parents[1]
_RESOURCES = _ROOT / 'src/ada/web/ui/core/resources'


def test_ada_ui_core_declares_foundational_assets_only() -> None:
    module = create_ada_ui_module()

    assert module.name == 'ada-ui'
    assert module.asset_layers == (ADA_UI_ASSET_LAYER,)
    assert ADA_UI_ASSET_LAYER.load_order == 100
    assert ADA_UI_ASSET_LAYER.package == 'ada.web.ui.core'
    assert module.register_callbacks is None
    assert module.register_routes is None


def test_ada_ui_core_owns_only_declared_css_resources() -> None:
    css_list = (_RESOURCES / 'css/css.list').read_text(encoding='utf-8').splitlines()

    assert css_list == ['10-tokens.css']
    assert all((_RESOURCES / 'css' / entry).is_file() for entry in css_list)
    assert not (_RESOURCES / 'css/00-bootstrap.min.css').exists()


def test_ada_ui_core_keeps_inter_but_does_not_reference_bootstrap_icons_cdn() -> None:
    module = create_ada_ui_module()
    fragments = module.index.head_fragments

    assert any('fonts.googleapis.com' in fragment for fragment in fragments)
    assert any('fonts.gstatic.com' in fragment for fragment in fragments)
    assert all('bootstrap-icons' not in fragment for fragment in fragments)
    assert all('jsdelivr.net' not in fragment for fragment in fragments)


def test_ada_ui_core_does_not_bundle_unrelated_runtime_capabilities() -> None:
    assert not (_RESOURCES / 'js').exists()
    assert not (_RESOURCES / 'img').exists()
    assert not (_RESOURCES / 'css/20-status.css').exists()
    assert not (_RESOURCES / 'css/30-page-ready.css').exists()


def test_ada_ui_core_module_matches_commented_mirror() -> None:
    productive = _ROOT / 'src/ada/web/ui/core/module.py'
    commented = _ROOT / 'commented/ada/web/ui/core/module.py'

    assert ast.dump(ast.parse(productive.read_text(encoding='utf-8'))) == ast.dump(
        ast.parse(commented.read_text(encoding='utf-8'))
    )
