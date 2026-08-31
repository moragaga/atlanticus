from dash import Dash

from ada.web.configuration.manager_tools import create_manager_tools_module


def test_module_registers_manager_and_source_editor_callbacks() -> None:
    app = Dash(__name__, use_pages=True, pages_folder='')
    module = create_manager_tools_module()

    assert module.register_callbacks is not None
    module.register_callbacks(app, object())

    assert len(app.callback_map) == 5
