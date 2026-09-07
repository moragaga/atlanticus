from __future__ import annotations

import ast
from pathlib import Path

from atlanticus.web.bootstrap import BOOTSTRAP_ASSET_LAYER, create_bootstrap_web_module


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


def test_bootstrap_assets_are_scoped_and_do_not_ship_reboot() -> None:
    entries = (CSS / 'css.list').read_text(encoding='utf-8').splitlines()
    source = '\n'.join((CSS / entry).read_text(encoding='utf-8') for entry in entries)

    assert entries == ['10_bootstrap_components.css', '20_atlanticus_theme.css']
    assert '.atlanticus-bootstrap .form-control' in source
    assert '.atlanticus-bootstrap .btn' in source
    assert ':root' not in source
    assert '\nbody {' not in source
    assert '\nhtml {' not in source
    assert '.container' not in source
    assert '.row {' not in source

    form_start = source.index('.atlanticus-bootstrap .form-control,')
    form_body_start = source.index('{', form_start)
    form_body_end = source.index('}', form_body_start)
    form_control = source[form_body_start + 1 : form_body_end]

    assert not any(
        line.strip() == 'width: 100%;'
        for line in form_control.splitlines()
    )
    assert 'max-width: 100%;' in form_control
    assert 'box-sizing: border-box;' in form_control


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
