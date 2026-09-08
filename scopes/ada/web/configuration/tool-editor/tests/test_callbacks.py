from dash import Dash, no_update

from ada.web.configuration.tool_editor import (
    register_tool_source_editor_callbacks,
    register_tool_structure_editor_callbacks,
)
from ada.web.configuration.tool_editor.structure_callbacks import (
    _new_key,
    _sanitize_linked_values,
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
def test_generated_internal_keys_are_stable_format_and_collision_safe() -> None:
    key = _new_key('cmp', ['cmp_existing'])

    assert key.startswith('cmp_')
    assert key != 'cmp_existing'
    assert ' ' not in key


def test_linked_values_drop_deleted_or_incompatible_components() -> None:
    assert _sanitize_linked_values(
        ['cmp_keep', 'cmp_removed'],
        [
            {
                'label': 'Keep',
                'value': 'cmp_keep',
            }
        ],
    ) == ['cmp_keep']

def test_add_component_does_not_require_completed_general_configuration() -> None:
    class CallbackApp:
        def __init__(self) -> None:
            self.callbacks: dict[str, object] = {}

        def callback(self, *_args, **_kwargs):
            def register(callback):
                self.callbacks[callback.__name__] = callback
                return callback

            return register

    app = CallbackApp()
    register_tool_structure_editor_callbacks(app)

    result = app.callbacks['add_component'](
        1,
        [],
        [],
        None,
        None,
        [],
        [],
    )

    assert result is not no_update
