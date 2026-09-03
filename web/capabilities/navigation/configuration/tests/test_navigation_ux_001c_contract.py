from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/navigation/configuration/resources/css/10_visual_normalization.css'


def test_ux_001c_navigation_modal_does_not_clip_dropdowns() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'max-height: none;' in css
    assert 'overflow: visible;' in css
    assert 'user-select: none;' in css


def test_ux_001c_navigation_focus_uses_atlanticus_ring() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'box-shadow: var(--atlanticus-admin-focus-ring) !important;' in css
