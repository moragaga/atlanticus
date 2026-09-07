from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/atlanticus/web/navigation/configuration'
CSS = SOURCE / 'resources/css'


def test_navigation_consumes_shared_controls_without_manager_css_contract() -> None:
    python = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (SOURCE / 'web').glob('*.py')
    )
    styles = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in CSS.glob('*.css')
    )
    assert 'atlanticus-ui-button' in python
    assert 'atlanticus-ui-select' in python
    assert 'atlanticus-ui-check' in python
    assert 'atlanticus-manager__button' not in python
    assert 'var(--atlanticus-manager-' not in styles
    assert 'var(--atlanticus-admin-' not in styles


def test_navigation_modal_does_not_restyle_shared_select() -> None:
    source = (CSS / '20_configuration_modal.css').read_text(encoding='utf-8')
    assert '.Select.is-focused > .Select-control' not in source
    assert '.Select-input > input:focus' not in source
