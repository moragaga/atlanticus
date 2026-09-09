from dash import Dash, no_update

from ada.web.configuration.tool_editor import (
    register_tool_source_editor_callbacks,
    register_tool_structure_editor_callbacks,
)
from ada.web.configuration.tool_editor.structure_callbacks import (
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


def test_coverage_waits_for_kind_and_restores_process_coverage() -> None:
    class CallbackApp:
        def __init__(self) -> None:
            self.callbacks: dict[str, object] = {}

        def callback(self, *_args, **_kwargs):
            def register(callback):
                self.callbacks[callback.__name__] = callback
                return callback

            return register

    app = CallbackApp()
    register_tool_source_editor_callbacks(app)

    assert app.callbacks['sync_coverage'](None, None, None, None) == (
        [],
        None,
        True,
        'Selecciona primero el tipo',
        None,
    )

    options, value, disabled, placeholder, remembered = app.callbacks['sync_coverage'](
        None,
        'integrated_operations',
        'plant',
        None,
    )
    assert [option['value'] for option in options] == ['mine_plant']
    assert value == 'mine_plant'
    assert disabled is True
    assert placeholder == 'Mina y Planta'
    assert remembered == 'plant'

    options, value, disabled, placeholder, remembered = app.callbacks['sync_coverage'](
        None,
        'process',
        'mine_plant',
        remembered,
    )
    assert [option['value'] for option in options] == ['mine', 'plant']
    assert value == 'plant'
    assert disabled is False
    assert placeholder == 'Seleccionar cobertura'
    assert remembered == 'plant'


def test_process_context_inherits_parent_and_integrated_clears_inherited_scope() -> None:
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

    hidden, scopes, disabled, linked_hidden, remembered_kind = app.callbacks[
        'update_context_fields'
    ](
        'process',
        'plant',
        [{'index': 0}, {'index': 1}],
        ['mine', None],
        [{'owner_index': 0}, {'owner_index': 1}],
        'process',
    )
    assert hidden == [False, False]
    assert scopes == ['plant', 'plant']
    assert disabled == [True, True]
    assert linked_hidden == [True, True]
    assert remembered_kind == 'process'

    hidden, scopes, disabled, linked_hidden, remembered_kind = app.callbacks[
        'update_context_fields'
    ](
        'integrated_operations',
        'mine_plant',
        [{'index': 0}, {'index': 1}],
        ['plant', 'plant'],
        [{'owner_index': 0}, {'owner_index': 1}],
        'process',
    )
    assert hidden == [False, False]
    assert scopes == [None, None]
    assert disabled == [False, False]
    assert linked_hidden == [False, False]
    assert remembered_kind == 'integrated_operations'

    _, scopes, _, _, remembered_kind = app.callbacks['update_context_fields'](
        'integrated_operations',
        'mine_plant',
        [{'index': 0}, {'index': 1}],
        ['mine', 'plant'],
        [{'owner_index': 0}, {'owner_index': 1}],
        'integrated_operations',
    )
    assert scopes == ['mine', 'plant']
    assert remembered_kind == 'integrated_operations'

    _, scopes, _, _, _ = app.callbacks['update_context_fields'](
        'integrated_operations',
        'mine_plant',
        [{'index': 0}, {'index': 1}, {'index': 2}],
        ['plant', 'plant', None],
        [{'owner_index': 0}, {'owner_index': 1}],
        'integrated_operations',
    )
    assert scopes == ['plant', 'plant', None]


def test_visible_also_in_refreshes_same_scope_components() -> None:
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

    result = app.callbacks['refresh_linked_component_options'](
        'integrated_operations',
        ['cmp_owner', 'cmp_visible'],
        ['Owner', 'Visible'],
        ['mine', 'mine'],
        [{'index': 0}, {'index': 1}],
        [{'index': 0, 'owner_index': 0}],
        [[]],
    )
    options, values, disabled, placeholders = result

    assert options == [[{'label': 'Visible', 'value': 'cmp_visible'}]]
    assert values == [[]]
    assert disabled == [False]
    assert placeholders == ['Seleccionar componentes compatibles']

    result = app.callbacks['refresh_linked_component_options'](
        'integrated_operations',
        ['cmp_owner', 'cmp_plant'],
        ['Owner', 'Plant'],
        ['mine', 'plant'],
        [{'index': 0}, {'index': 1}],
        [{'index': 0, 'owner_index': 0}],
        [[]],
    )
    options, _, disabled, placeholders = result

    assert options == [[]]
    assert disabled == [True]
    assert placeholders == ['No hay componentes compatibles']


def test_tool_key_is_generated_once_and_survives_rename() -> None:
    class CallbackApp:
        def __init__(self) -> None:
            self.callbacks: dict[str, object] = {}

        def callback(self, *_args, **_kwargs):
            def register(callback):
                self.callbacks[callback.__name__] = callback
                return callback

            return register

    app = CallbackApp()
    register_tool_source_editor_callbacks(app)

    key = app.callbacks['sync_tool_key'](
        None,
        'Flotación Área Húmeda',
        None,
    )
    assert key is not None
    assert key.startswith('tool_flotacion_area_humeda_')

    renamed = app.callbacks['sync_tool_key'](
        None,
        'Flotación Rougher',
        key,
    )
    assert renamed == key


def test_visible_also_in_survives_unrelated_component_addition() -> None:
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

    options, values, disabled, _ = app.callbacks['refresh_linked_component_options'](
        'integrated_operations',
        ['cmp_owner', 'cmp_visible', 'cmp_new'],
        ['Owner', 'Visible', 'Nuevo'],
        ['plant', 'plant', None],
        [{'index': 0}, {'index': 1}, {'index': 2}],
        [{'index': 0, 'owner_index': 0}],
        [['cmp_visible']],
    )

    assert options == [[{'label': 'Visible', 'value': 'cmp_visible'}]]
    assert values == [['cmp_visible']]
    assert disabled == [False]


def test_component_key_materializes_once_from_first_name() -> None:
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

    generated = app.callbacks['stabilize_component_keys'](
        ['Carguío', 'Carguío'],
        [None, None],
    )

    assert generated[0].startswith('cmp_carguio_')
    assert generated[1].startswith('cmp_carguio_')
    assert generated[0] != generated[1]

    renamed = app.callbacks['stabilize_component_keys'](
        ['Carguío Mina', 'Carguío Planta'],
        generated,
    )
    assert renamed == generated


def test_subcomponent_key_materializes_once_and_removes_accents() -> None:
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

    generated = app.callbacks['stabilize_subcomponent_keys'](
        ['Extracción N° 1'],
        [None],
    )
    key = generated[0]

    assert key.startswith('sub_extraccion_n_1_')
    assert key.isascii()

    renamed = app.callbacks['stabilize_subcomponent_keys'](
        ['CAEX principal'],
        generated,
    )
    assert renamed == generated
