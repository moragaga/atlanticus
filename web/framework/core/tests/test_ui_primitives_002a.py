from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/resources/base/css'


def test_shared_control_layer_is_part_of_base_assets() -> None:
    entries = (CSS / 'css.list').read_text(encoding='utf-8').splitlines()
    assert entries == ['00_tokens.css', '10_shell.css', '20_controls.css']


def test_shared_controls_define_visual_semantics_without_layout_widths() -> None:
    source = (CSS / '20_controls.css').read_text(encoding='utf-8')
    assert '.atlanticus-ui-button--primary' in source
    assert '.atlanticus-ui-button--secondary' in source
    assert '.atlanticus-ui-button--danger' in source
    assert '.atlanticus-ui-icon-button' in source
    assert '.atlanticus-ui-select .Select-control' in source
    assert '.atlanticus-ui-check' in source
    assert 'width:' not in source
    assert 'max-width:' not in source
    assert 'height:' not in source
    assert 'min-height:' not in source


def test_shared_tokens_do_not_use_manager_namespace() -> None:
    source = (CSS / '00_tokens.css').read_text(encoding='utf-8')
    assert '--atlanticus-ui-primary:' in source
    assert '--atlanticus-ui-accent:' in source
    assert '--atlanticus-manager-' not in source
