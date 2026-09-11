from __future__ import annotations

import ast
from pathlib import Path

from atlanticus.web.bootstrap import (
    BOOTSTRAP_ASSET_LAYER,
    create_bootstrap_web_module,
)

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/bootstrap/resources/css'
SOURCE = ROOT / 'src/atlanticus/web/bootstrap'
COMMENTED = ROOT / 'commented/atlanticus/web/bootstrap'


def test_bootstrap_module_is_opt_in_asset_only() -> None:
    module = create_bootstrap_web_module()

    assert module.name == 'bootstrap'
    assert module.asset_layers == (BOOTSTRAP_ASSET_LAYER,)
    assert BOOTSTRAP_ASSET_LAYER.load_order == 40
    assert module.register_services is None
    assert module.register_callbacks is None


def test_bootstrap_integration_css_manifest_resolves_existing_files() -> None:
    entries = (CSS / 'css.list').read_text(encoding='utf-8').splitlines()

    assert entries == ['10_bootstrap_components.css', '20_atlanticus_theme.css']
    assert all((CSS / entry).is_file() for entry in entries)


def test_productive_and_commented_python_are_ast_equivalent() -> None:
    for source in SOURCE.glob('*.py'):
        mirror = COMMENTED / source.name
        assert mirror.exists()
        assert ast.dump(
            ast.parse(source.read_text(encoding='utf-8')),
            include_attributes=False,
        ) == ast.dump(
            ast.parse(mirror.read_text(encoding='utf-8')),
            include_attributes=False,
        )
