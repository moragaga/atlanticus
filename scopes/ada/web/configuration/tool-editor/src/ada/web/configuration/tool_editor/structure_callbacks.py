from __future__ import annotations

from collections.abc import Mapping

from dash import ALL, MATCH, Input, Output, Patch, State, ctx, no_update

from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor.ids import CONFIGURATION_STORE_ID
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
    COMPONENT_SCOPE_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    STRUCTURE_ADD_COMPONENT_ID,
    STRUCTURE_COMPONENTS_CONTAINER_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_KIND_ID,
    STRUCTURE_KPI_DESTINATIONS_ID,
    STRUCTURE_OPERATIONAL_SCOPE_ID,
    STRUCTURE_OPERATIONAL_SCOPE_WRAPPER_ID,
    STRUCTURE_VALIDATION_MESSAGE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    SUBCOMPONENT_DELETE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
)
from ada.web.configuration.tool_editor.structure_presentation import (
    _kind_label,
    build_component_editor_row,
    build_subcomponent_editor_row,
)


def register_tool_structure_editor_callbacks(app: object) -> None:
    @app.callback(
        Output(STRUCTURE_COMPONENTS_CONTAINER_ID, 'children'),
        Output(STRUCTURE_OPERATIONAL_SCOPE_ID, 'value'),
        Output(STRUCTURE_OPERATIONAL_SCOPE_WRAPPER_ID, 'hidden'),
        Output(STRUCTURE_KIND_ID, 'children'),
        Input(CONFIGURATION_STORE_ID, 'data'),
    )
    def load_structure_editor(
        configuration_document: dict[str, object] | None,
    ):
        if configuration_document is None:
            return [], None, True, 'Sin configuración'
        configuration = ToolConfiguration.from_document(configuration_document)
        components, subcomponents, operational_scope = (
            structure_editor_table_data_from_configuration(configuration)
        )
        kind = configuration.kind
        nested_rows = _subcomponent_rows_by_owner(subcomponents)
        return (
            [
                build_component_editor_row(
                    index=index,
                    row=row,
                    kind=kind,
                    subcomponent_rows=nested_rows.get(
                        str(row.get('key') or '').strip(),
                        (),
                    ),
                    all_component_rows=components,
                )
                for index, row in enumerate(components)
            ],
            operational_scope,
            kind is not ToolConfigurationKind.PROCESS,
            _kind_label(kind),
        )

    @app.callback(
        Output(
            STRUCTURE_COMPONENTS_CONTAINER_ID,
            'children',
            allow_duplicate=True,
        ),
        Input(STRUCTURE_ADD_COMPONENT_ID, 'n_clicks'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_component(
        clicks: int | None,
        component_ids: list[dict[str, object]],
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        configuration_document: dict[str, object] | None,
    ):
        if not _click_is_real(clicks) or configuration_document is None:
            return no_update
        configuration = ToolConfiguration.from_document(configuration_document)
        patch = Patch()
        patch.append(
            build_component_editor_row(
                index=_next_index(component_ids),
                row=None,
                kind=configuration.kind,
                all_component_rows=list(
                    _component_rows_from_values(
                        ids=component_ids,
                        keys=component_keys,
                        names=component_names,
                        scopes=component_scopes,
                    ).values()
                ),
            )
        )
        return patch

    @app.callback(
        Output(
            STRUCTURE_COMPONENTS_CONTAINER_ID,
            'children',
            allow_duplicate=True,
        ),
        Input({'type': COMPONENT_DELETE_TYPE, 'index': ALL}, 'n_clicks'),
        State({'type': COMPONENT_DELETE_TYPE, 'index': ALL}, 'id'),
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
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_subcomponent(
        clicks: int | None,
        add_button_id: dict[str, object],
        subcomponent_ids: list[dict[str, object]],
        component_ids: list[dict[str, object]],
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        configuration_document: dict[str, object] | None,
    ):
        if not _click_is_real(clicks) or configuration_document is None:
            return no_update
        owner_index = _owner_index(add_button_id)
        if owner_index < 0:
            return no_update
        configuration = ToolConfiguration.from_document(configuration_document)
        rows = _component_rows_from_values(
            ids=component_ids,
            keys=component_keys,
            names=component_names,
            scopes=component_scopes,
        )
        patch = Patch()
        patch.append(
            build_subcomponent_editor_row(
                index=_next_index(subcomponent_ids),
                owner_index=owner_index,
                row=None,
                kind=configuration.kind,
                linked_component_options=_linked_options_from_rows(
                    rows,
                    owner_index=owner_index,
                ),
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
            {
                'type': SUBCOMPONENT_LINKED_TYPE,
                'index': ALL,
                'owner_index': ALL,
            },
            'options',
        ),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
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
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        component_ids: list[dict[str, object]],
        linked_ids: list[dict[str, object]],
    ):
        rows = _component_rows_from_values(
            ids=component_ids,
            keys=component_keys,
            names=component_names,
            scopes=component_scopes,
        )
        return [
            _linked_options_from_rows(
                rows,
                owner_index=_owner_index(linked_id),
            )
            for linked_id in linked_ids
        ]

    @app.callback(
        Output(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDITY_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDATION_MESSAGE_ID, 'children'),
        Output(STRUCTURE_KPI_DESTINATIONS_ID, 'children'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_LAYOUT_ROLE_TYPE, 'index': ALL}, 'value'),
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
        Input(STRUCTURE_OPERATIONAL_SCOPE_ID, 'value'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_LAYOUT_ROLE_TYPE, 'index': ALL}, 'id'),
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
        State(CONFIGURATION_STORE_ID, 'data'),
    )
    def validate_structure(
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        component_layout_roles: list[object],
        subcomponent_keys: list[object],
        subcomponent_names: list[object],
        subcomponent_links: list[object],
        operational_scope: object,
        component_key_ids: list[dict[str, object]],
        component_name_ids: list[dict[str, object]],
        component_scope_ids: list[dict[str, object]],
        component_layout_ids: list[dict[str, object]],
        subcomponent_key_ids: list[dict[str, object]],
        subcomponent_name_ids: list[dict[str, object]],
        subcomponent_link_ids: list[dict[str, object]],
        configuration_document: dict[str, object] | None,
    ):
        if configuration_document is None:
            return None, False, '', '—'
        try:
            configuration = ToolConfiguration.from_document(configuration_document)
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
                operational_scope=operational_scope,
            )
        except ValueError as error:
            return None, False, str(error), '—'
        return (
            structure.to_document(),
            True,
            '',
            ', '.join(structure.kpi_destination_keys),
        )


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
    owner_by_subcomponent = {
        component_id['index']: component_id['owner_index']
        for component_id in key_ids
        if _index_from_id(component_id) is not None
        and _owner_index(component_id) >= 0
    }
    return [
        {
            'owner_component_key': component_keys.get(
                owner_by_subcomponent.get(index)
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
        index = _index_from_id(component_id)
        if index is not None:
            resolved[index] = value
    return resolved


def _component_rows_from_values(
    *,
    ids: list[dict[str, object]],
    keys: list[object],
    names: list[object],
    scopes: list[object],
) -> dict[int, dict[str, object]]:
    resolved: dict[int, dict[str, object]] = {}
    for position, component_id in enumerate(ids):
        index = _index_from_id(component_id)
        if index is None:
            continue
        resolved[index] = {
            'key': keys[position] if position < len(keys) else None,
            'display_name': (
                names[position] if position < len(names) else None
            ),
            'scope': (
                scopes[position] if position < len(scopes) else None
            ),
        }
    return resolved


def _linked_options_from_rows(
    rows: Mapping[int, Mapping[str, object]],
    *,
    owner_index: int,
) -> list[dict[str, str]]:
    owner = rows.get(owner_index)
    if owner is None:
        return []
    owner_scope = str(owner.get('scope') or '').strip()
    if not owner_scope:
        return []
    options: list[dict[str, str]] = []
    for index, row in rows.items():
        if index == owner_index:
            continue
        if str(row.get('scope') or '').strip() != owner_scope:
            continue
        key = str(row.get('key') or '').strip()
        if not key:
            continue
        display_name = str(row.get('display_name') or '').strip()
        options.append({'label': display_name or key, 'value': key})
    return options


def _subcomponent_rows_by_owner(
    rows: list[dict[str, object]],
) -> dict[str, list[tuple[int, dict[str, object]]]]:
    resolved: dict[str, list[tuple[int, dict[str, object]]]] = {}
    for index, row in enumerate(rows):
        owner_key = str(row.get('owner_component_key') or '').strip()
        resolved.setdefault(owner_key, []).append((index, row))
    return resolved


def _index_from_id(component_id: Mapping[str, object]) -> int | None:
    value = component_id.get('index')
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _owner_index(component_id: Mapping[str, object]) -> int:
    value = component_id.get('owner_index')
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return -1


def _next_index(ids: list[dict[str, object]]) -> int:
    indexes = [
        value
        for component_id in ids
        if (value := _index_from_id(component_id)) is not None
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
