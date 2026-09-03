from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / 'src/atlanticus/web/users/configuration/web/layout.py'
CALLBACKS = ROOT / 'src/atlanticus/web/users/configuration/web/callbacks.py'
CSS = ROOT / 'src/atlanticus/web/users/configuration/resources/css/10_visual_normalization.css'


def test_ux_001c_uses_pending_identity_language() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert "'Pendientes'" in source
    assert 'Identidades pendientes de incorporación' in source
    assert 'Microsoft Entra ID' in source
    assert "'Descubiertos'" not in source
    assert 'Usuarios descubiertos' not in source


def test_ux_001c_discovery_failure_is_non_blocking_notice() -> None:
    source = CALLBACKS.read_text(encoding='utf-8')
    assert "_notice('No fue posible actualizar las identidades pendientes.')" in source
    assert 'atlanticus-users-admin__message--notice' in source


def test_ux_001c_removes_native_action_tooltips() -> None:
    layout = LAYOUT.read_text(encoding='utf-8')
    callbacks = CALLBACKS.read_text(encoding='utf-8')
    assert "title=f'Seleccionar {label.lower()}'" not in layout
    assert "title='Cerrar'" not in layout
    assert 'El perfil está asignado a usuarios' not in callbacks


def test_ux_001c_modal_does_not_clip_dropdowns() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'max-height: none;' in css
    assert 'overflow: visible;' in css
    assert 'user-select: none;' in css
