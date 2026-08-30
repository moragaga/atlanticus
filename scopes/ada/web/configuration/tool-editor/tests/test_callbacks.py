from dash import Dash

from ada.web.configuration.tool_editor import register_tool_source_editor_callbacks
from ada.web.configuration.tool_editor.ids import (
    DISPATCH_FIELDS_ID,
    DRAFT_STORE_ID,
    PI_PRE_DEGRADING_ID,
)


def test_callback_registration_exposes_source_editor_flows() -> None:
    app = Dash(__name__)

    register_tool_source_editor_callbacks(app)

    callback_keys = tuple(app.callback_map)
    assert any(PI_PRE_DEGRADING_ID in key for key in callback_keys)
    assert any(DISPATCH_FIELDS_ID in key for key in callback_keys)
    assert any(DRAFT_STORE_ID in key for key in callback_keys)
