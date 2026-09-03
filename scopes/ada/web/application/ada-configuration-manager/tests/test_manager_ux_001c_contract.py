from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / 'src/ada/web/application/configuration_manager/composition.py'
TOOLS = ROOT / 'src/ada/web/application/configuration_manager/tools.py'


def test_ux_001c_names_tool_module_as_herramienta() -> None:
    source = COMPOSITION.read_text(encoding='utf-8')
    assert "title='Herramienta'" in source
    assert "title='Tool'" not in source
    assert 'Configuración de la herramienta operacional de esta aplicación.' in source


def test_ux_001c_uses_spanish_tool_history_identifier() -> None:
    source = TOOLS.read_text(encoding='utf-8')
    assert "_history_item('Identificador', configuration.tool_key)" in source
    assert "_history_item('Tool key', configuration.tool_key)" not in source
