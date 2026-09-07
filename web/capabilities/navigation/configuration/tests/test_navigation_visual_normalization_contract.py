from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / 'src/atlanticus/web/navigation/configuration/resources/css'


def test_navigation_visual_normalization_layer_is_registered() -> None:
    entries = (CSS_ROOT / 'css.list').read_text(encoding='utf-8').splitlines()
    assert entries[-1] == '20_configuration_modal.css'


def test_navigation_fields_use_shared_manager_controls() -> None:
    css = (CSS_ROOT / '10_visual_normalization.css').read_text(encoding='utf-8')
    shared_controls = (
        Path(__file__).resolve().parents[4]
        / 'framework/core/src/atlanticus/web/resources/base/css/20_controls.css'
    ).read_text(encoding='utf-8')

    assert 'var(--atlanticus-admin-control-height)' not in css
    assert 'background: var(--atlanticus-ui-control-disabled);' not in css
    assert 'background: var(--atlanticus-ui-control-disabled);' in shared_controls


def test_navigation_modal_uses_shared_manager_shell_tokens() -> None:
    css = (CSS_ROOT / '10_visual_normalization.css').read_text(encoding='utf-8')
    assert 'var(--atlanticus-ui-overlay)' in css
    assert 'var(--atlanticus-ui-modal-radius)' in css
    assert 'var(--atlanticus-ui-modal-shadow)' in css
    assert 'border-top: .24rem solid var(--atlanticus-ui-accent);' in css
