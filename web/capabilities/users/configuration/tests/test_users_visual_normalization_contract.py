from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / 'src/atlanticus/web/users/configuration/resources/css'


def test_users_visual_normalization_layer_is_registered() -> None:
    entries = (CSS_ROOT / 'css.list').read_text(encoding='utf-8').splitlines()
    assert entries[-1] == '10_visual_normalization.css'


def test_users_tabs_and_reference_fields_use_normalized_contract() -> None:
    css = (CSS_ROOT / '10_visual_normalization.css').read_text(encoding='utf-8')
    assert '.atlanticus-users-admin__tabs {' in css
    assert 'border-bottom: 1px solid var(--atlanticus-manager-border);' in css
    assert '.atlanticus-users-admin__field--reference code {' in css
    assert 'background: var(--atlanticus-manager-control-disabled);' in css


def test_users_modal_uses_shared_manager_shell_tokens() -> None:
    css = (CSS_ROOT / '10_visual_normalization.css').read_text(encoding='utf-8')
    assert 'var(--atlanticus-manager-overlay)' in css
    assert 'var(--atlanticus-manager-modal-radius)' in css
    assert 'var(--atlanticus-manager-modal-shadow)' in css
