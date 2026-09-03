from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/navigation/configuration/resources/css/10_visual_normalization.css'
LAYOUT = ROOT / 'src/atlanticus/web/navigation/configuration/web/layout.py'


def test_ux_001b_navigation_uses_generic_local_actions() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert 'Importar archivo de Navigation' not in source
    assert 'Guardar borrador de Navigation' not in source
    assert 'Borrador de Navigation' not in source
    assert 'Borrador local · navegación' in source


def test_ux_001b_navigation_uses_spanish_identifier_label() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert "'Key'," not in source
    assert source.count("'Identificador',") >= 2


def test_ux_001b_navigation_modal_has_atlanticus_header_without_horizontal_scroll() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'background: var(--atlanticus-manager-color-primary-action);' in css
    assert 'overflow-x: hidden;' in css
