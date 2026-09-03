from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'src/atlanticus/web/manager/resources/css/30_visual_normalization.css'
LAYOUT = ROOT / 'src/atlanticus/web/manager/web/layout.py'


def test_ux_001b_keeps_home_pagination_at_page_bottom() -> None:
    css = CSS.read_text(encoding='utf-8')
    assert 'margin-top: auto;' in css
    assert 'overflow-x: hidden;' in css


def test_ux_001b_groups_workflow_sections() -> None:
    css = CSS.read_text(encoding='utf-8')
    source = LAYOUT.read_text(encoding='utf-8')
    assert 'atlanticus-manager__workflow-status--draft' in source
    assert 'atlanticus-manager__workflow-status--published' in source
    assert 'display: contents;' in css


def test_ux_001b_uses_generic_workflow_actions_and_spanish_status() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert "'Validar borrador'" not in source
    assert "f'Verificar {module.source_name}'" not in source
    assert "f'Guardar en {module.source_name}'" not in source
    assert "f'Proyectar en {module.projection_name}'" not in source
    assert 'Configuration status could not be loaded' not in source
    assert 'Configuration status is unavailable' not in source


def test_ux_001b_removes_native_sidebar_tooltip() -> None:
    source = LAYOUT.read_text(encoding='utf-8')
    assert "title='Abrir configuraciones'" not in source
    assert "title='Cerrar configuraciones'" not in source
