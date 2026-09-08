# Espejo comentado de callbacks del editor estructural anidado.

from __future__ import annotations

from collections.abc import Mapping

from dash import (
    ALL,
    MATCH,
    Input,
    Output,
    Patch,
    State,
    ctx,
    no_update,
)

from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor.ids import (
    CONFIGURATION_STORE_ID,
    COVERAGE_ID,
    DRAFT_STORE_ID,
    KIND_ID,
)
from ada.web.configuration.tool_editor.structure import (
    build_structure_from_editor_tables,
    structure_editor_table_data_from_configuration,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_ADD_SUBCOMPONENT_TYPE,
    COMPONENT_DELETE_TYPE,
    COMPONENT_DISPLAY_NAME_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_LAYOUT_ROLE_TYPE,
    COMPONENT_LAYOUT_WRAPPER_TYPE,
    COMPONENT_SCOPE_TYPE,
    COMPONENT_SCOPE_WRAPPER_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    STRUCTURE_ADD_COMPONENT_ID,
    STRUCTURE_COMPONENTS_CONTAINER_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_VALIDATION_MESSAGE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    SUBCOMPONENT_DELETE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_LINKED_WRAPPER_TYPE,
)
from ada.web.configuration.tool_editor.structure_presentation import (
    _linked_component_options,
    build_component_editor_row,
    build_subcomponent_editor_row,
)

_COVERAGE_MINE_PLANT = 'mine_plant'


def register_tool_structure_editor_callbacks(app: object) -> None:
    @app.callback(
        Output(STRUCTURE_COMPONENTS_CONTAINER_ID, 'children'),
        Input(CONFIGURATION_STORE_ID, 'data'),
    )
    def load_structure_editor(
        configuration_document: dict[str, object] | None,
    ):
        if configuration_document is None:
            return []
        configuration = ToolConfiguration.from_document(configuration_document)
        components, subcomponents, coverage = (
            structure_editor_table_data_from_configuration(configuration)
        )
        nested_rows = _subcomponent_rows_by_owner(subcomponents)
        return [
            build_component_editor_row(
                index=index,
                row=row,
                kind=configuration.kind,
                coverage=coverage,
                subcomponent_rows=nested_rows.get(
                    str(row.get('key') or ''),
                    (),
                ),
                all_component_rows=components,
            )
            for index, row in enumerate(components)
        ]

    @app.callback(
        Output(
            STRUCTURE_COMPONENTS_CONTAINER_ID,
            'children',
            allow_duplicate=True,
        ),
        Input(STRUCTURE_ADD_COMPONENT_ID, 'n_clicks'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State(KIND_ID, 'value'),
        State(COVERAGE_ID, 'value'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        State(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        prevent_initial_call=True,
    )
    def add_component(
        clicks: int | None,
        component_ids: list[dict[str, object]],
        kind_value: str | None,
        coverage: str | None,
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
    ):
        if (
            not _click_is_real(clicks)
            or kind_value is None
            or coverage is None
        ):
            return no_update
        try:
            kind = ToolConfigurationKind(kind_value)
        except ValueError:
            return no_update
        rows = _component_rows_from_values(
            ids=component_ids,
            keys=component_keys,
            names=component_names,
            scopes=component_scopes,
        )
        patch = Patch()
        patch.append(
            build_component_editor_row(
                index=_next_index(component_ids),
                row=None,
                kind=kind,
                coverage=coverage,
                all_component_rows=list(rows.values()),
            )
        )
        return patch

    @app.callback(
        Output(
            STRUCTURE_COMPONENTS_CONTAINER_ID,
            'children',
            allow_duplicate=True,
        ),
        Input(
            {'type': COMPONENT_DELETE_TYPE, 'index': ALL},
            'n_clicks',
        ),
        State(
            {'type': COMPONENT_DELETE_TYPE, 'index': ALL},
            'id',
        ),
        prevent_initial_call=True,
    )
    def delete_component(
        clicks: list[int | None],
        button_ids: list[dict[str, object]],
    ):
        position = _triggered_position(clicks, button_ids)
        if position is None:
            return no_update
        patch = Patch()
        del patch[position]
        return patch

    @app.callback(
        Output(
            {
                'type': COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
                'owner_index': MATCH,
            },
            'children',
            allow_duplicate=True,
        ),
        Input(
            {
                'type': COMPONENT_ADD_SUBCOMPONENT_TYPE,
                'owner_index': MATCH,
            },
            'n_clicks',
        ),
        State(
            {
                'type': COMPONENT_ADD_SUBCOMPONENT_TYPE,
                'owner_index': MATCH,
            },
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        State(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State(KIND_ID, 'value'),
        State(COVERAGE_ID, 'value'),
        prevent_initial_call=True,
    )
# Agrega el Subcomponent directamente en el Component propietario.
    def add_subcomponent(
        clicks: int | None,
        add_button_id: dict[str, object],
        subcomponent_ids: list[dict[str, object]],
        component_ids: list[dict[str, object]],
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        kind_value: str | None,
        coverage: str | None,
    ):
        if (
            not _click_is_real(clicks)
            or kind_value is None
            or coverage is None
        ):
            return no_update
        owner_index = _owner_index(add_button_id)
        if owner_index < 0:
            return no_update
        try:
            kind = ToolConfigurationKind(kind_value)
        except ValueError:
            return no_update
        rows = _component_rows_from_values(
            ids=component_ids,
            keys=component_keys,
            names=component_names,
            scopes=component_scopes,
        )
        linked_options = (
            _linked_component_options(
                list(rows.values()),
                owner_index=_owner_position(rows, owner_index),
                coverage=coverage,
            )
            if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
            else []
        )
        patch = Patch()
        patch.append(
            build_subcomponent_editor_row(
                index=_next_index(subcomponent_ids),
                owner_index=owner_index,
                row=None,
                linked_hidden=(
                    kind is not ToolConfigurationKind.INTEGRATED_OPERATIONS
                ),
                linked_component_options=linked_options,
            )
        )
        return patch

    @app.callback(
        Output(
            {
                'type': COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
                'owner_index': MATCH,
            },
            'children',
            allow_duplicate=True,
        ),
        Input(
            {
                'type': SUBCOMPONENT_DELETE_TYPE,
                'index': ALL,
                'owner_index': MATCH,
            },
            'n_clicks',
        ),
        State(
            {
                'type': SUBCOMPONENT_DELETE_TYPE,
                'index': ALL,
                'owner_index': MATCH,
            },
            'id',
        ),
        prevent_initial_call=True,
    )
    def delete_subcomponent(
        clicks: list[int | None],
        button_ids: list[dict[str, object]],
    ):
        position = _triggered_position(clicks, button_ids)
        if position is None:
            return no_update
        patch = Patch()
        del patch[position]
        return patch

    @app.callback(
        Output(
            {'type': COMPONENT_SCOPE_WRAPPER_TYPE, 'index': ALL},
            'hidden',
        ),
        Output(
            {'type': COMPONENT_LAYOUT_WRAPPER_TYPE, 'index': ALL},
            'hidden',
        ),
        Output(
            {'type': COMPONENT_SCOPE_TYPE, 'index': ALL},
            'value',
        ),
        Output(
            {
                'type': SUBCOMPONENT_LINKED_WRAPPER_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'hidden',
        ),
        Input(KIND_ID, 'value'),
        Input(COVERAGE_ID, 'value'),
        State(
            {'type': COMPONENT_SCOPE_WRAPPER_TYPE, 'index': ALL},
            'id',
        ),
        State(
            {'type': COMPONENT_LAYOUT_WRAPPER_TYPE, 'index': ALL},
            'id',
        ),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State(
            {
                'type': SUBCOMPONENT_LINKED_WRAPPER_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
    )
# Tipo y cobertura controlan qué campos estructurales son relevantes.
    def update_context_fields(
        kind_value: str | None,
        coverage: str | None,
        scope_wrapper_ids: list[dict[str, object]],
        layout_wrapper_ids: list[dict[str, object]],
        current_scopes: list[object],
        linked_wrapper_ids: list[dict[str, object]],
    ):
        integrated = (
            kind_value == ToolConfigurationKind.INTEGRATED_OPERATIONS.value
        )
        process = kind_value == ToolConfigurationKind.PROCESS.value
        mixed = integrated and coverage == _COVERAGE_MINE_PLANT
        if integrated and coverage in {'mine', 'plant'}:
            scope_values = [coverage for _ in current_scopes]
        elif mixed:
            scope_values = list(current_scopes)
        else:
            scope_values = [None for _ in current_scopes]
        return (
            [not mixed for _ in scope_wrapper_ids],
            [not process for _ in layout_wrapper_ids],
            scope_values,
            [not integrated for _ in linked_wrapper_ids],
        )

    @app.callback(
        Output(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'options',
        ),
        Input(KIND_ID, 'value'),
        Input(COVERAGE_ID, 'value'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
        Input({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
    )
    def refresh_linked_component_options(
        kind_value: str | None,
        coverage: str | None,
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        component_ids: list[dict[str, object]],
        linked_ids: list[dict[str, object]],
    ):
        if (
            kind_value != ToolConfigurationKind.INTEGRATED_OPERATIONS.value
            or coverage is None
        ):
            return [[] for _ in linked_ids]
        rows = _component_rows_from_values(
            ids=component_ids,
            keys=component_keys,
            names=component_names,
            scopes=component_scopes,
        )
        ordered = list(rows.values())
        return [
            _linked_component_options(
                ordered,
                owner_index=_owner_position(
                    rows,
                    _owner_index(linked_id),
                ),
                coverage=coverage,
            )
            for linked_id in linked_ids
        ]

    @app.callback(
        Output(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDITY_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDATION_MESSAGE_ID, 'children'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
        Input({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        Input(
            {'type': COMPONENT_LAYOUT_ROLE_TYPE, 'index': ALL},
            'value',
        ),
        Input(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
        Input(
            {
                'type': SUBCOMPONENT_DISPLAY_NAME_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
        Input(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
        Input(COVERAGE_ID, 'value'),
        Input(DRAFT_STORE_ID, 'data'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'id',
        ),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'id'),
        State(
            {'type': COMPONENT_LAYOUT_ROLE_TYPE, 'index': ALL},
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_DISPLAY_NAME_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
        State(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
    )
# La estructura se valida junto al borrador base de la Tool.
    def validate_structure(
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        component_layout_roles: list[object],
        subcomponent_keys: list[object],
        subcomponent_names: list[object],
        subcomponent_links: list[object],
        coverage: object,
        source_document: dict[str, object] | None,
        component_key_ids: list[dict[str, object]],
        component_name_ids: list[dict[str, object]],
        component_scope_ids: list[dict[str, object]],
        component_layout_ids: list[dict[str, object]],
        subcomponent_key_ids: list[dict[str, object]],
        subcomponent_name_ids: list[dict[str, object]],
        subcomponent_link_ids: list[dict[str, object]],
    ):
        if source_document is None:
            return None, False, ''
        try:
            configuration = ToolConfiguration.from_document(source_document)
            component_key_values = _indexed_values(
                component_key_ids,
                component_keys,
            )
            structure = build_structure_from_editor_tables(
                base_configuration=configuration,
                component_rows=_component_rows(
                    keys=component_key_values,
                    names=_indexed_values(
                        component_name_ids,
                        component_names,
                    ),
                    scopes=_indexed_values(
                        component_scope_ids,
                        component_scopes,
                    ),
                    layout_roles=_indexed_values(
                        component_layout_ids,
                        component_layout_roles,
                    ),
                ),
                subcomponent_rows=_subcomponent_rows(
                    key_ids=subcomponent_key_ids,
                    keys=_indexed_values(
                        subcomponent_key_ids,
                        subcomponent_keys,
                    ),
                    names=_indexed_values(
                        subcomponent_name_ids,
                        subcomponent_names,
                    ),
                    links=_indexed_values(
                        subcomponent_link_ids,
                        subcomponent_links,
                    ),
                    component_keys=component_key_values,
                ),
                coverage=coverage,
            )
        except ValueError as error:
            return None, False, str(error)
        return structure.to_document(), True, ''


def _component_rows(
    *,
    keys: Mapping[int, object],
    names: Mapping[int, object],
    scopes: Mapping[int, object],
    layout_roles: Mapping[int, object],
) -> list[dict[str, object]]:
    return [
        {
            'key': value,
            'display_name': names.get(index),
            'scope': scopes.get(index),
            'layout_role': layout_roles.get(index),
        }
        for index, value in keys.items()
    ]


def _subcomponent_rows(
    *,
    key_ids: list[dict[str, object]],
    keys: Mapping[int, object],
    names: Mapping[int, object],
    links: Mapping[int, object],
    component_keys: Mapping[int, object],
) -> list[dict[str, object]]:
    owner_indexes = {
        component_id.get('index'): component_id.get('owner_index')
        for component_id in key_ids
        if (
            isinstance(component_id.get('index'), int)
            and not isinstance(component_id.get('index'), bool)
        )
    }
    return [
        {
            'owner_component_key': component_keys.get(
                owner_indexes.get(index)
            ),
            'key': value,
            'display_name': names.get(index),
            'linked_component_keys': links.get(index, []),
        }
        for index, value in keys.items()
    ]


def _indexed_values(
    ids: list[dict[str, object]],
    values: list[object],
) -> dict[int, object]:
    resolved: dict[int, object] = {}
    for component_id, value in zip(ids, values, strict=True):
        index = component_id.get('index')
        if isinstance(index, int) and not isinstance(index, bool):
            resolved[index] = value
    return resolved


def _component_rows_from_values(
    *,
    ids: list[dict[str, object]],
    keys: list[object],
    names: list[object],
    scopes: list[object],
) -> dict[int, dict[str, object]]:
    key_by_index = _indexed_values(ids, keys)
    name_by_index = {
        component_id['index']: value
        for component_id, value in zip(ids, names, strict=True)
        if (
            isinstance(component_id.get('index'), int)
            and not isinstance(component_id.get('index'), bool)
        )
    }
    scope_by_index = {
        component_id['index']: value
        for component_id, value in zip(ids, scopes, strict=False)
        if (
            isinstance(component_id.get('index'), int)
            and not isinstance(component_id.get('index'), bool)
        )
    }
    return {
        index: {
            'key': value,
            'display_name': name_by_index.get(index),
            'scope': scope_by_index.get(index),
        }
        for index, value in key_by_index.items()
    }


def _subcomponent_rows_by_owner(
    rows: list[dict[str, object]],
) -> dict[str, list[tuple[int, dict[str, object]]]]:
    resolved: dict[str, list[tuple[int, dict[str, object]]]] = {}
    for index, row in enumerate(rows):
        owner_key = str(row.get('owner_component_key') or '').strip()
        resolved.setdefault(owner_key, []).append((index, row))
    return resolved


def _owner_index(component_id: Mapping[str, object]) -> int:
    value = component_id.get('owner_index')
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return -1


def _owner_position(
    rows: Mapping[int, Mapping[str, object]],
    owner_index: int,
) -> int:
    for position, index in enumerate(rows):
        if index == owner_index:
            return position
    return -1


def _next_index(ids: list[dict[str, object]]) -> int:
    indexes = [
        value
        for component_id in ids
        if (
            isinstance((value := component_id.get('index')), int)
            and not isinstance(value, bool)
        )
    ]
    return max(indexes, default=-1) + 1


def _triggered_position(
    clicks: list[int | None],
    button_ids: list[dict[str, object]],
) -> int | None:
    triggered_id = ctx.triggered_id
    if not isinstance(triggered_id, dict):
        return None
    for position, (click_count, button_id) in enumerate(
        zip(clicks, button_ids, strict=True)
    ):
        if button_id == triggered_id and _click_is_real(click_count):
            return position
    return None


def _click_is_real(clicks: int | None) -> bool:
    return (
        isinstance(clicks, int)
        and not isinstance(clicks, bool)
        and clicks > 0
    )
