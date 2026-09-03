from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / 'src/atlanticus/web/manager/resources/css'


def test_visual_normalization_layer_is_registered_after_home() -> None:
    entries = (CSS_ROOT / 'css.list').read_text(encoding='utf-8').splitlines()
    assert '20_home.css' in entries
    assert entries[-1] == '30_visual_normalization.css'


def test_visual_normalization_enforces_single_row_desktop_workflow() -> None:
    css = (CSS_ROOT / '30_visual_normalization.css').read_text(encoding='utf-8')
    assert 'grid-template-columns: repeat(5, minmax(0, 1fr));' in css
    assert '.atlanticus-manager__workflow-actions {' in css
    assert 'display: grid;' in css


def test_visual_normalization_owns_dropdown_and_overflow_contracts() -> None:
    css = (CSS_ROOT / '30_visual_normalization.css').read_text(encoding='utf-8')
    assert '.atlanticus-manager .Select-control {' in css
    assert 'overflow-x: clip;' in css
    assert '--atlanticus-manager-border-strong:' in css
    assert '--atlanticus-manager-color-accent:' in css
    assert '--atlanticus-manager-text-soft:' in css
