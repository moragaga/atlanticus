from dash import Dash

from ada.web.configuration.tool_editor import (
    register_tool_source_editor_callbacks,
    register_tool_structure_editor_callbacks,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_ADD_SUBCOMPONENT_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    SUBCOMPONENT_DELETE_TYPE,
)


def test_complete_tool_callback_graph_registers() -> None:
    app = Dash(__name__)
    register_tool_source_editor_callbacks(app)
    register_tool_structure_editor_callbacks(app)

    assert app.callback_map


def test_nested_pattern_contract_uses_owner_index() -> None:
    app = Dash(__name__)
    register_tool_structure_editor_callbacks(app)

    rendered = '\n'.join(str(value) for value in app.callback_map.values())

    assert COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE in rendered
    assert COMPONENT_ADD_SUBCOMPONENT_TYPE in rendered
    assert SUBCOMPONENT_DELETE_TYPE in rendered
    assert 'owner_index' in rendered
