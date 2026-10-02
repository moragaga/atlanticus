import ada.kpis.connections as package


def test_public_api():
    assert package.__version__ == '1.0.0'
    assert callable(package.read_connection_registry)
    assert callable(package.require_tool_key)
