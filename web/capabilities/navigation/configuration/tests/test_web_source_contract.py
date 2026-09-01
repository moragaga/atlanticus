from pathlib import Path


def _web_source() -> str:
    root = Path(__file__).parents[1] / 'src/atlanticus/web/navigation/configuration/web'
    return '\n'.join(path.read_text(encoding='utf-8') for path in root.glob('*.py'))


def test_navigation_editor_keeps_simple_administrative_surface() -> None:
    source = _web_source()

    assert 'Página principal' not in source
    assert 'Definir como home' not in source
    assert 'Claves adicionales' not in source
    assert 'Heredar permisos' not in source
    assert 'Expandida por defecto' not in source
    assert 'necesario para logout' not in source
    assert 'Perfiles con acceso' in source
    assert 'multi=True' in source
    assert 'Sin sección / raíz' in source


def test_navigation_configuration_web_remains_standalone() -> None:
    source = _web_source()

    assert 'atlanticus.web.users' not in source
    assert 'ada.' not in source


def test_dynamic_navigation_actions_require_a_real_click() -> None:
    source = _web_source()

    assert 'def _triggered_click_is_real() -> bool:' in source
    assert source.count('and _triggered_click_is_real()') >= 3
    assert source.count('or not _triggered_click_is_real()') >= 2


def test_navigation_editor_keeps_source_revision_loaded_with_editor_content() -> None:
    source = _web_source()

    assert 'SOURCE_REVISION_STORE_ID' in source
    assert "State(SOURCE_REVISION_STORE_ID, 'data')" in source
    assert '_current_source_revision' not in source
