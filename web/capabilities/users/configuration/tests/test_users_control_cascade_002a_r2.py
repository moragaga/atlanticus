from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'src/atlanticus/web/users/configuration/web'
CSS = ROOT / 'src/atlanticus/web/users/configuration/resources/css'


def test_users_inputs_and_modal_skin_consume_shared_primitives() -> None:
    layout = (WEB / 'layout.py').read_text(encoding='utf-8')
    assert layout.count("className='atlanticus-ui-input'") >= 3
    assert 'atlanticus-ui-modal-header' in layout
    assert layout.count('atlanticus-ui-modal-body') >= 2
    assert 'atlanticus-ui-modal-footer' in layout


def test_users_composition_no_longer_owns_input_focus_visuals() -> None:
    styles = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in CSS.glob('*.css')
    )
    assert '.atlanticus-users-admin__field > input:focus' not in styles
    assert '.atlanticus-users-admin__field > input:focus-visible' not in styles


def test_users_tabs_and_local_actions_expose_pointer() -> None:
    source = (CSS / '00_users_admin.css').read_text(encoding='utf-8')
    tab = source[source.index('.atlanticus-users-admin__tab {'):]
    action = source[source.index('.atlanticus-users-admin__action {'):]
    assert 'cursor: pointer;' in tab.split('}', 1)[0]
    assert 'cursor: pointer;' in action.split('}', 1)[0]
