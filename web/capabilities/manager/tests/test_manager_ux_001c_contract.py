from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / 'src/atlanticus/web/manager/web/layout.py'
CSS = ROOT / 'src/atlanticus/web/manager/resources/css/30_visual_normalization.css'


def test_ux_001c_keeps_published_state_visible_when_status_is_missing() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert source.count("'Estado publicado'") >= 3
    assert 'Aún no existe una configuración publicada.' in source
    assert 'No fue posible consultar el estado publicado en este momento.' in source
    assert 'atlanticus-manager__workflow-group--published-empty' in source


def test_ux_001c_uses_pointer_and_atlanticus_focus() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'cursor: pointer !important;' in css
    assert 'accent-color: var(--atlanticus-manager-color-primary) !important;' in css
    assert 'box-shadow: var(--atlanticus-admin-focus-ring) !important;' in css


def test_ux_001c_does_not_hide_inner_overflow_to_mask_geometry() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'overflow-x: visible;' in css
    assert 'width: calc(100% - 1rem);' in css


def test_ux_001c_strengthens_manager_home_without_workflow_changes() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert '.atlanticus-manager__home-card::before' in css
    assert 'min-height: calc(100dvh - 10.5rem);' in css
