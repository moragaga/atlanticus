from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'src/atlanticus/web/navigation/configuration/web'
CSS = ROOT / 'src/atlanticus/web/navigation/configuration/resources/css'


def test_navigation_inputs_and_selects_consume_shared_primitives() -> None:
    layout = (WEB / 'layout.py').read_text(encoding='utf-8')
    assert layout.count("className='atlanticus-ui-input'") >= 7
    assert layout.count("className='atlanticus-ui-select'") >= 2
    assert 'atlanticus-ui-modal-header' in layout
    assert 'atlanticus-ui-modal-body' in layout
    assert 'atlanticus-ui-modal-footer' in layout


def test_navigation_modals_have_header_close_actions() -> None:
    layout = (WEB / 'layout.py').read_text(encoding='utf-8')
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')
    assert "LINK_CANCEL_ID + '-header'" in layout
    assert "GROUP_CANCEL_ID + '-header'" in layout
    assert "Input(LINK_CANCEL_ID + '-header', 'n_clicks')" in callbacks
    assert "Input(GROUP_CANCEL_ID + '-header', 'n_clicks')" in callbacks


def test_navigation_composition_no_longer_owns_input_or_select_focus_visuals() -> None:
    styles = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in CSS.glob('*.css')
    )
    assert '.atlanticus-navigation-admin__field input:focus' not in styles
    assert '.atlanticus-navigation-admin__field input:focus-visible' not in styles
    assert '.Select.is-focused > .Select-control' not in styles
    assert '.Select-input > input:focus' not in styles
