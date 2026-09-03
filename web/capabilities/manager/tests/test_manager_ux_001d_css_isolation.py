from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_DIR = ROOT / 'src/atlanticus/web/manager/resources/css'
CSS = CSS_DIR / '40_interaction_surface.css'


def test_ux_001d_terminal_manager_css_is_loaded_last() -> None:
    entries = (CSS_DIR / 'css.list').read_text(encoding='utf-8').splitlines()
    assert entries[-1] == '40_interaction_surface.css'


def test_ux_001d_workflow_uses_explicit_rows_without_forced_height() -> None:
    source = CSS.read_text(encoding='utf-8')
    assert 'grid-row: 1;' in source
    assert 'grid-row: 2;' in source
    assert 'grid-row: 3;' in source
    assert 'height: auto !important;' in source


def test_ux_001d_explicit_interactive_classes_have_pointer() -> None:
    source = CSS.read_text(encoding='utf-8')
    assert '.atlanticus-manager__button:not(:disabled)' in source
    assert '.atlanticus-manager__icon-button:not(:disabled)' in source
    assert '.atlanticus-manager__tab:not(:disabled)' in source
    assert 'cursor: pointer !important;' in source


def test_ux_001d_home_adds_blue_and_sidebar_separation() -> None:
    source = CSS.read_text(encoding='utf-8')
    assert 'rgba(38, 66, 90, .075)' in source
    assert 'border-left: .18rem solid rgba(38, 66, 90, .42);' in source
    assert '.atlanticus-manager__sidebar-link--home +' in source
