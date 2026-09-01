from dash import Dash

from ada.web.configuration.manager_tools import create_manager_tools_module
from ada.web.configuration.manager_tools.ids import BRANDING_VARIANT_ID
from ada.web.configuration.tool_editor.ids import PI_PRE_DEGRADING_ID
from ada.web.configuration.tool_editor.structure_ids import (
    STRUCTURE_COMPONENTS_CONTAINER_ID,
)


def test_module_registers_manager_sources_and_structure_callbacks() -> None:
    app = Dash(__name__, use_pages=True, pages_folder='')
    module = create_manager_tools_module()

    assert module.register_callbacks is not None
    module.register_callbacks(app, object())

    callback_contract = repr(app.callback_map)

    assert BRANDING_VARIANT_ID in callback_contract
    assert PI_PRE_DEGRADING_ID in callback_contract
    assert STRUCTURE_COMPONENTS_CONTAINER_ID in callback_contract
