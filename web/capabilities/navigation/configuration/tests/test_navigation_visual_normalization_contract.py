from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / 'src/atlanticus/web/navigation/configuration/resources/css'


def test_navigation_visual_normalization_layer_is_registered() -> None:
    entries = (CSS_ROOT / 'css.list').read_text(encoding='utf-8').splitlines()
    assert entries[-1] == '10_visual_normalization.css'


def test_navigation_fields_use_shared_manager_controls() -> None:
    css = (CSS_ROOT / '10_visual_normalization.css').read_text(encoding='utf-8')
    assert 'min-height: var(--atlanticus-admin-control-height);' in css
    assert 'background: var(--atlanticus-manager-control-disabled);' in css


def test_navigation_modal_uses_shared_manager_shell_tokens() -> None:
    css = (CSS_ROOT / '10_visual_normalization.css').read_text(encoding='utf-8')
    assert 'var(--atlanticus-manager-overlay)' in css
    assert 'var(--atlanticus-manager-modal-radius)' in css
    assert 'var(--atlanticus-manager-modal-shadow)' in css
    assert 'border-top: .24rem solid var(--atlanticus-manager-color-primary);' in css
