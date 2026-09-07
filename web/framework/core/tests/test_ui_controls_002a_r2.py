from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/resources/base/css'


def test_form_primitives_have_single_shared_visual_owner() -> None:
    controls = (CSS / '20_controls.css').read_text(encoding='utf-8')
    assert '.atlanticus-ui-input {' in controls
    assert '.atlanticus-ui-select .Select-control {' in controls
    assert '.atlanticus-ui-check label {' in controls
    assert '.atlanticus-ui-modal-header {' in controls
    assert '.atlanticus-ui-modal-body,' in controls
    assert '.atlanticus-ui-modal-footer {' in controls


def test_form_selection_uses_atlanticus_blue_not_gold() -> None:
    controls = (CSS / '20_controls.css').read_text(encoding='utf-8')
    assert 'accent-color: var(--atlanticus-ui-secondary);' in controls
    assert 'border-color: var(--atlanticus-ui-control-focus);' in controls
    assert 'background: var(--atlanticus-ui-selection-soft)' in controls


def test_shared_icon_button_does_not_own_close_geometry() -> None:
    controls = (CSS / '20_controls.css').read_text(encoding='utf-8')
    start = controls.index('\n.atlanticus-ui-icon-button {\n    display: inline-grid;') + 1
    block = controls[
        start:
        controls.index(
            '.atlanticus-ui-icon-button:hover:not(:disabled)',
            start,
        )
    ]
    assert 'padding:' not in block
    assert 'width:' not in block
    assert 'height:' not in block
