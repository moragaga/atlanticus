from __future__ import annotations

from collections.abc import Mapping

from dash import ALL, Input, Output, Patch, State, ctx, no_update

from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor.ids import CONFIGURATION_STORE_ID
from ada.web.configuration.tool_editor.structure import (
    build_structure_from_editor_tables,
    structure_editor_table_data_from_configuration,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_DELETE_TYPE,
    COMPONENT_DISPLAY_NAME_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_LAYOUT_ROLE_TYPE,
    COMPONENT_SCOPE_TYPE,
    STRUCTURE_ADD_COMPONENT_ID,
    STRUCTURE_ADD_SUBCOMPONENT_ID,
    STRUCTURE_COMPONENTS_CONTAINER_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_KIND_ID,
    STRUCTURE_KPI_DESTINATIONS_ID,
    STRUCTURE_OPERATIONAL_SCOPE_ID,
    STRUCTURE_OPERATIONAL_SCOPE_WRAPPER_ID,
    STRUCTURE_SUBCOMPONENTS_CONTAINER_ID,
    STRUCTURE_VALIDATION_MESSAGE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    SUBCOMPONENT_DELETE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_OWNER_TYPE,
)
from ada.web.configuration.tool_editor.structure_presentation import (
    _component_options,
    _kind_label,
    build_component_editor_row,
    build_subcomponent_editor_row,
)


def register_tool_structure_editor_callbacks(app: object) -> None:
    @app.callback(
        Output(STRUCTURE_COMPONENTS_CONTAINER_ID, 'children'),
        Output(STRUCTURE_SUBCOMPONENTS_CONTAINER_ID, 'children'),
        Output(STRUCTURE_OPERATIONAL_SCOPE_ID, 'value'),
        Output(STRUCTURE_OPERATIONAL_SCOPE_WRAPPER_ID, 'hidden'),
        Output(STRUCTURE_KIND_ID, 'children'),
        Input(CONFIGURATION_STORE_ID, 'data'),
    )
    def load_structure_editor(configuration_document: dict[str, object] | None):
        if configuration_document is None:
            return [], [], None, True, 'Sin configuración'
        configuration = ToolConfiguration.from_document(configuration_document)
        components, subcomponents, operational_scope = (
            structure_editor_table_data_from_configuration(configuration)
        )
        kind = configuration.kind
        options = _component_options(components)
        return (
            [
                build_component_editor_row(
                    index=index,
                    row=row,
                    kind=kind,
                )
                for index, row in enumerate(components)
            ],
            [
                build_subcomponent_editor_row(
                    index=index,
                    row=row,
                    kind=kind,
                    component_options=options,
                )
                for index, row in enumerate(subcomponents)
            ],
            operational_scope,
            kind is not ToolConfigurationKind.PROCESS,
            _kind_label(kind),
        )

    @app.callback(
        Output(STRUCTURE_COMPONENTS_CONTAINER_ID, 'children', allow_duplicate=True),
        Input(STRUCTURE_ADD_COMPONENT_ID, 'n_clicks'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_component(
        clicks: int | None,
        component_ids: list[dict[str, object]],
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
            )
        )
        return patch

    @app.callback(
        Output(STRUCTURE_COMPONENTS_CONTAINER_ID, 'children', allow_duplicate=True),
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
        Output(STRUCTURE_SUBCOMPONENTS_CONTAINER_ID, 'children', allow_duplicate=True),
        Input(STRUCTURE_ADD_SUBCOMPONENT_ID, 'n_clicks'),
        State({'type': SUBCOMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_subcomponent(
        clicks: int | None,
        subcomponent_ids: list[dict[str, object]],
        component_keys: list[object],
        component_names: list[object],
        configuration_document: dict[str, object] | None,
    ):
        if not _click_is_real(clicks) or configuration_document is None:
            return no_update
        configuration = ToolConfiguration.from_document(configuration_document)
        options = _component_options_from_values(component_keys, component_names)
        patch = Patch()
        patch.append(
            build_subcomponent_editor_row(
                index=_next_index(subcomponent_ids),
                row=None,
                kind=configuration.kind,
                component_options=options,
            )
        )
        return patch

    @app.callback(
        Output(STRUCTURE_SUBCOMPONENTS_CONTAINER_ID, 'children', allow_duplicate=True),
        Input({'type': SUBCOMPONENT_DELETE_TYPE, 'index': ALL}, 'n_clicks'),
        State({'type': SUBCOMPONENT_DELETE_TYPE, 'index': ALL}, 'id'),
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
        Output({'type': SUBCOMPONENT_OWNER_TYPE, 'index': ALL}, 'options'),
        Output({'type': SUBCOMPONENT_LINKED_TYPE, 'index': ALL}, 'options'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        State({'type': SUBCOMPONENT_OWNER_TYPE, 'index': ALL}, 'id'),
        State({'type': SUBCOMPONENT_LINKED_TYPE, 'index': ALL}, 'id'),
    )
    def refresh_component_options(
        component_keys: list[object],
        component_names: list[object],
        owner_ids: list[dict[str, object]],
        linked_ids: list[dict[str, object]],
    ):
        options = _component_options_from_values(component_keys, component_names)
        return (
            [options for _ in owner_ids],
            [options for _ in linked_ids],
        )

    @app.callback(
        Output(STRUCTURE_DOCUMENT_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDITY_STORE_ID, 'data'),
        Output(STRUCTURE_VALIDATION_MESSAGE_ID, 'children'),
        Output(STRUCTURE_KPI_DESTINATIONS_ID, 'children'),
        Input({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'value'),
        Input({'type': COMPONENT_LAYOUT_ROLE_TYPE, 'index': ALL}, 'value'),
        Input({'type': SUBCOMPONENT_OWNER_TYPE, 'index': ALL}, 'value'),
        Input({'type': SUBCOMPONENT_KEY_TYPE, 'index': ALL}, 'value'),
        Input({'type': SUBCOMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'value'),
        Input({'type': SUBCOMPONENT_LINKED_TYPE, 'index': ALL}, 'value'),
        Input(STRUCTURE_OPERATIONAL_SCOPE_ID, 'value'),
        State({'type': COMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_SCOPE_TYPE, 'index': ALL}, 'id'),
        State({'type': COMPONENT_LAYOUT_ROLE_TYPE, 'index': ALL}, 'id'),
        State({'type': SUBCOMPONENT_OWNER_TYPE, 'index': ALL}, 'id'),
        State({'type': SUBCOMPONENT_KEY_TYPE, 'index': ALL}, 'id'),
        State({'type': SUBCOMPONENT_DISPLAY_NAME_TYPE, 'index': ALL}, 'id'),
        State({'type': SUBCOMPONENT_LINKED_TYPE, 'index': ALL}, 'id'),
        State(CONFIGURATION_STORE_ID, 'data'),
    )
    def validate_structure(
        component_keys: list[object],
        component_names: list[object],
        component_scopes: list[object],
        component_layout_roles: list[object],
        subcomponent_owners: list[object],
        subcomponent_keys: list[object],
        subcomponent_names: list[object],
        subcomponent_links: list[object],
        operational_scope: object,
        component_key_ids: list[dict[str, object]],
        component_name_ids: list[dict[str, object]],
        component_scope_ids: list[dict[str, object]],
        component_layout_ids: list[dict[str, object]],
        subcomponent_owner_ids: list[dict[str, object]],
        subcomponent_key_ids: list[dict[str, object]],
        subcomponent_name_ids: list[dict[str, object]],
        subcomponent_link_ids: list[dict[str, object]],
        configuration_document: dict[str, object] | None,
    ):
        if configuration_document is None:
            return None, False, '', '—'
        try:
            configuration = ToolConfiguration.from_document(configuration_document)
            structure = build_structure_from_editor_tables(
                base_configuration=configuration,
                component_rows=_component_rows(
                    keys=_indexed_values(component_key_ids, component_keys),
                    names=_indexed_values(component_name_ids, component_names),
                    scopes=_indexed_values(component_scope_ids, component_scopes),
                    layout_roles=_indexed_values(
                        component_layout_ids,
                        component_layout_roles,
                    ),
                ),
                subcomponent_rows=_subcomponent_rows(
                    owners=_indexed_values(
                        subcomponent_owner_ids,
                        subcomponent_owners,
                    ),
                    keys=_indexed_values(subcomponent_key_ids, subcomponent_keys),
                    names=_indexed_values(subcomponent_name_ids, subcomponent_names),
                    links=_indexed_values(
                        subcomponent_link_ids,
                        subcomponent_links,
                    ),
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
    owners: Mapping[int, object],
    keys: Mapping[int, object],
    names: Mapping[int, object],
    links: Mapping[int, object],
) -> list[dict[str, object]]:
    return [
        {
            'owner_component_key': owners.get(index),
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


def _component_options_from_values(
    keys: list[object],
    names: list[object],
) -> list[dict[str, str]]:
    rows = [
        {
            'key': key,
            'display_name': name,
        }
        for key, name in zip(keys, names, strict=True)
    ]
    return _component_options(rows)


def _next_index(ids: list[dict[str, object]]) -> int:
    indexes = [
        value
        for component_id in ids
        if isinstance((value := component_id.get('index')), int) and not isinstance(value, bool)
    ]
    return max(indexes, default=-1) + 1


def _triggered_position(
    clicks: list[int | None],
    button_ids: list[dict[str, object]],
) -> int | None:
    triggered_id = ctx.triggered_id
    if not isinstance(triggered_id, dict):
        return None
    for position, (click_count, button_id) in enumerate(zip(clicks, button_ids, strict=True)):
        if button_id == triggered_id and _click_is_real(click_count):
            return position
    return None


def _click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0
