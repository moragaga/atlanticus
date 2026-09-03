from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/users/configuration/resources/css/10_visual_normalization.css'
LAYOUT = ROOT / 'src/atlanticus/web/users/configuration/web/layout.py'
CALLBACKS = ROOT / 'src/atlanticus/web/users/configuration/web/callbacks.py'


def test_ux_001b_users_uses_generic_local_actions() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert 'Importar archivo de Users' not in source
    assert 'Guardar borrador de Users' not in source
    assert 'Borrador de Users · perfiles y usuarios' not in source
    assert 'Borrador local · perfiles y usuarios' in source


def test_ux_001b_users_modal_has_atlanticus_header_without_horizontal_scroll() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'background: var(--atlanticus-manager-color-primary-action);' in css
    assert 'overflow-x: hidden;' in css


def test_ux_001b_users_visible_discovery_error_is_spanish() -> None:
    source = CALLBACKS.read_text(encoding='utf-8')
    assert 'Discovered users could not be loaded' not in source
    assert 'No fue posible cargar las identidades pendientes.' in source
