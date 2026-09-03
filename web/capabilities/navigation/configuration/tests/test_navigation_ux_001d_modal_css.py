from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_DIR = ROOT / 'src/atlanticus/web/navigation/configuration/resources/css'
CSS = CSS_DIR / '20_configuration_modal.css'


def test_ux_001d_navigation_modal_css_is_terminal_and_scoped() -> None:
    entries = (CSS_DIR / 'css.list').read_text(encoding='utf-8').splitlines()
    assert entries[-1] == '20_configuration_modal.css'
    source = CSS.read_text(encoding='utf-8')
    assert '.atlanticus-navigation-admin__modal-card' in source
    assert '.atlanticus-users-admin' not in source


def test_ux_001d_navigation_modal_restores_rounding() -> None:
    source = CSS.read_text(encoding='utf-8')
    assert 'overflow: hidden !important;' in source
    assert 'border-radius: var(--atlanticus-manager-modal-radius) !important;' in source


def test_ux_001d_navigation_select_has_one_focus_owner() -> None:
    source = CSS.read_text(encoding='utf-8')
    assert '.Select.is-focused > .Select-control' in source
    assert '.Select-input > input:focus' in source
    assert 'box-shadow: none !important;' in source
