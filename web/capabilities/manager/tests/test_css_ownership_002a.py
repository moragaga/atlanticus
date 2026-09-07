from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/atlanticus/web/manager'
CSS = SOURCE / 'resources/css'


def test_manager_does_not_own_shared_button_or_select_primitives() -> None:
    python = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (SOURCE / 'web').glob('*.py')
    )
    manager_css = (CSS / '10_manager.css').read_text(encoding='utf-8')
    visual_css = (CSS / '30_visual_normalization.css').read_text(encoding='utf-8')
    assert 'atlanticus-manager__button' not in python
    assert 'atlanticus-manager__icon-button' not in python
    assert 'atlanticus-manager__button' not in manager_css
    assert 'atlanticus-manager__icon-button' not in manager_css
    assert '.atlanticus-manager .Select' not in visual_css


def test_manager_css_does_not_redeclare_document_shell() -> None:
    manager_css = (CSS / '10_manager.css').read_text(encoding='utf-8')
    visual_css = (CSS / '30_visual_normalization.css').read_text(encoding='utf-8')
    assert not manager_css.lstrip().startswith('html,')
    assert '#react-entry-point' not in visual_css
    assert '#_dash-app-content' not in visual_css
