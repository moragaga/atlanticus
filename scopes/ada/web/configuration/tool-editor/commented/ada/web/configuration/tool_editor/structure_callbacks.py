# Espejo comentado de callbacks estructurales R2.

from __future__ import annotations

from collections.abc import Mapping
from secrets import token_hex

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

from ada.configuration.tools import (
    ToolConfiguration,
    ToolConfigurationKind,
)
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
    COMPONENT_SCOPE_TYPE,
    COMPONENT_SCOPE_WRAPPER_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    COMPONENT_SUMMARY_COUNT_TYPE,
    COMPONENT_SUMMARY_NAME_TYPE,
    COMPONENT_SUMMARY_SCOPE_TYPE,
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
    SUBCOMPONENT_SUMMARY_LINK_TYPE,
    SUBCOMPONENT_SUMMARY_NAME_TYPE,
)
from ada.web.configuration.tool_editor.structure_presentation import (
    _linked_component_options,
    _linked_values,
    _shared_label,
    _subcomponent_count_label,
    _summary_scope,
    build_component_editor_row,
    build_subcomponent_editor_row,
)


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
        configuration = ToolConfiguration.from_document(
            configuration_document
        )
        components, subcomponents, coverage = (
            structure_editor_table_data_from_configuration(
                configuration
            )
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
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'data'),
        State(KIND_ID, 'value'),
        State(COVERAGE_ID, 'value'),
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
        component_keys: list[object],
        kind_value: str | None,
        coverage: str | None,
        component_names: list[object],
        component_scopes: list[object],
    ):
        # Crear la fila no depende de que Información general ya esté completa.
        if not _click_is_real(clicks):
            return no_update
        kind = None
        if kind_value is not None:
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
                row={
                    'key': _new_key('cmp', component_keys),
                    'display_name': '',
                    'scope': None,
                },
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
        State(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'data',
        ),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'data'),
        State(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State(KIND_ID, 'value'),
        prevent_initial_call=True,
    )
    def add_subcomponent(
        clicks: int | None,
        add_button_id: dict[str, object],
        subcomponent_ids: list[dict[str, object]],
        subcomponent_keys: list[object],
        component_ids: list[dict[str, object]],
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        kind_value: str | None,
    ):
        if not _click_is_real(clicks) or kind_value is None:
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
            )
            if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
            else []
        )

        patch = Patch()
        patch.append(
            build_subcomponent_editor_row(
                index=_next_index(subcomponent_ids),
                owner_index=owner_index,
                row={
                    'key': _new_key('sub', subcomponent_keys),
                    'display_name': '',
                    'linked_component_keys': [],
                },
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
        State(
            {'type': COMPONENT_SCOPE_WRAPPER_TYPE, 'index': ALL},
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
    def update_context_fields(
        kind_value: str | None,
        scope_wrapper_ids: list[dict[str, object]],
        current_scopes: list[object],
        linked_wrapper_ids: list[dict[str, object]],
    ):
        integrated = (
            kind_value
            == ToolConfigurationKind.INTEGRATED_OPERATIONS.value
        )
        return (
            [not integrated for _ in scope_wrapper_ids],
            (
                list(current_scopes)
                if integrated
                else [None for _ in current_scopes]
            ),
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
        Output(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
        Input(KIND_ID, 'value'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'data'),
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
        State(
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'value',
        ),
    )
# Los links se limpian si el Component destino se elimina o deja de ser compatible.
    def refresh_linked_component_options(
        kind_value: str | None,
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        component_ids: list[dict[str, object]],
        linked_ids: list[dict[str, object]],
        linked_values: list[object],
    ):
        if (
            kind_value
            != ToolConfigurationKind.INTEGRATED_OPERATIONS.value
        ):
            empty = [[] for _ in linked_ids]
            return empty, [list(value) for value in empty]

        rows = _component_rows_from_values(
            ids=component_ids,
            keys=component_keys,
            names=component_names,
            scopes=component_scopes,
        )
        ordered = list(rows.values())
        options = [
            _linked_component_options(
                ordered,
                owner_index=_owner_position(
                    rows,
                    _owner_index(linked_id),
                ),
            )
            for linked_id in linked_ids
        ]
        values = [
            _sanitize_linked_values(
                current,
                available,
            )
            for current, available in zip(
                linked_values,
                options,
                strict=True,
            )
        ]
        return options, values

    @app.callback(
        Output(
            {'type': COMPONENT_SUMMARY_NAME_TYPE, 'index': ALL},
            'children',
        ),
        Input(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
    )
    def sync_component_names(names: list[object]):
        return [
            str(name or '').strip() or 'Nuevo componente'
            for name in names
        ]

    @app.callback(
        Output(
            {'type': COMPONENT_SUMMARY_SCOPE_TYPE, 'index': ALL},
            'children',
        ),
        Input(KIND_ID, 'value'),
        Input(COVERAGE_ID, 'value'),
        Input({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
    )
    def sync_component_context(
        kind_value: str | None,
        coverage: str | None,
        scopes: list[object],
    ):
        try:
            kind = (
                ToolConfigurationKind(kind_value)
                if kind_value
                else None
            )
        except ValueError:
            kind = None
        return [
            _summary_scope(
                kind=kind,
                coverage=coverage,
                scope=scope,
            )
            for scope in scopes
        ]

    @app.callback(
        Output(
            {'type': COMPONENT_SUMMARY_COUNT_TYPE, 'index': ALL},
            'children',
        ),
        Input(
            {
                'type': COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
                'owner_index': ALL,
            },
            'children',
        ),
    )
    def sync_component_counts(rows: list[object]):
        return [
            _subcomponent_count_label(_children_count(row))
            for row in rows
        ]

    @app.callback(
        Output(
            {
                'type': SUBCOMPONENT_SUMMARY_NAME_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'children',
        ),
        Output(
            {
                'type': SUBCOMPONENT_SUMMARY_LINK_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'children',
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
    )
    def sync_subcomponent_summaries(
        names: list[object],
        links: list[object],
    ):
        return (
            [
                str(name or '').strip() or 'Nuevo subcomponente'
                for name in names
            ],
            [
                _shared_label(_linked_values(link))
                for link in links
            ],
        )

    @app.callback(
        Output(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDITY_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDATION_MESSAGE_ID, 'children'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'data'),
        Input(
            {'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL},
            'value',
        ),
        Input({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        Input(
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'data',
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
            {
                'type': SUBCOMPONENT_KEY_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'id',
        ),
    )
    def validate_structure(
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        subcomponent_keys: list[object],
        subcomponent_names: list[object],
        subcomponent_links: list[object],
        coverage: object,
        source_document: dict[str, object] | None,
        component_key_ids: list[dict[str, object]],
        subcomponent_key_ids: list[dict[str, object]],
    ):
        if source_document is None:
            return None, False, ''
        if _editor_is_incomplete(
            component_ids=component_key_ids,
            component_names=component_names,
            component_scopes=component_scopes,
            subcomponent_ids=subcomponent_key_ids,
            subcomponent_names=subcomponent_names,
            kind_value=str(source_document.get('kind') or ''),
        ):
            return None, False, ''

        try:
            configuration = ToolConfiguration.from_document(
                source_document
            )
            component_key_values = _indexed_values(
                component_key_ids,
                component_keys,
            )
            structure = build_structure_from_editor_tables(
                base_configuration=configuration,
                component_rows=_component_rows(
                    keys=component_key_values,
                    names=_indexed_values(
                        component_key_ids,
                        component_names,
                    ),
                    scopes=_indexed_values(
                        component_key_ids,
                        component_scopes,
                    ),
                ),
                subcomponent_rows=_subcomponent_rows(
                    key_ids=subcomponent_key_ids,
                    keys=_indexed_values(
                        subcomponent_key_ids,
                        subcomponent_keys,
                    ),
                    names=_indexed_values(
                        subcomponent_key_ids,
                        subcomponent_names,
                    ),
                    links=_indexed_values(
                        subcomponent_key_ids,
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
) -> list[dict[str, object]]:
    return [
        {
            'key': value,
            'display_name': names.get(index),
            'scope': scopes.get(index),
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
    name_by_index = _indexed_values(ids, names)
    scope_by_index = _indexed_values(ids, scopes)
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
    resolved: dict[
        str,
        list[tuple[int, dict[str, object]]],
    ] = {}
    for index, row in enumerate(rows):
        owner_key = str(
            row.get('owner_component_key') or ''
        ).strip()
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
            isinstance(
                (value := component_id.get('index')),
                int,
            )
            and not isinstance(value, bool)
        )
    ]
    return max(indexes, default=-1) + 1


# Las keys internas nacen una sola vez y no se exponen como campos editables.
def _new_key(prefix: str, existing: list[object]) -> str:
    occupied = {
        str(value)
        for value in existing
        if value is not None
    }
    while True:
        candidate = f'{prefix}_{token_hex(6)}'
        if candidate not in occupied:
            return candidate


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


def _children_count(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    return 1



def _sanitize_linked_values(
    value: object,
    options: list[dict[str, str]],
) -> list[str]:
    allowed = {
        option['value']
        for option in options
    }
    return [
        item
        for item in _linked_values(value)
        if item in allowed
    ]

def _editor_is_incomplete(
    *,
    component_ids: list[dict[str, object]],
    component_names: list[object],
    component_scopes: list[object],
    subcomponent_ids: list[dict[str, object]],
    subcomponent_names: list[object],
    kind_value: str,
) -> bool:
    if not component_ids:
        return True
    if any(
        not str(name or '').strip()
        for name in component_names
    ):
        return True
    integrated = (
        kind_value
        == ToolConfigurationKind.INTEGRATED_OPERATIONS.value
    )
    if integrated:
        resolved_scopes = {
            str(scope or '').strip()
            for scope in component_scopes
            if str(scope or '').strip()
        }
        if resolved_scopes != {'mine', 'plant'}:
            return True
    if any(
        not str(name or '').strip()
        for name in subcomponent_names
    ):
        return True
    owners = {
        item.get('owner_index')
        for item in subcomponent_ids
    }
    component_indexes = {
        item.get('index')
        for item in component_ids
    }
    return not component_indexes.issubset(owners)
