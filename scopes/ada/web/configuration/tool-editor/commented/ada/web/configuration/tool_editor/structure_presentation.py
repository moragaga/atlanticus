from __future__ import annotations

# Compone Components y Subcomponents con controles Dash normales, sin grillas especializadas.
from collections.abc import Mapping, Sequence

from dash import dcc, html
from dash.development.base_component import Component

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolConfiguration,
    ToolConfigurationKind,
    ToolScope,
)
from ada.web.configuration.tool_editor.structure import (
    structure_editor_table_data_from_configuration,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_DELETE_TYPE,
    COMPONENT_DISPLAY_NAME_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_LAYOUT_ROLE_TYPE,
    COMPONENT_ROW_TYPE,
    COMPONENT_SCOPE_TYPE,
    STRUCTURE_ADD_COMPONENT_ID,
    STRUCTURE_ADD_SUBCOMPONENT_ID,
    STRUCTURE_COMPONENTS_CONTAINER_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_KIND_ID,
    STRUCTURE_KPI_DESTINATIONS_ID,
    STRUCTURE_OPERATIONAL_SCOPE_ID,
    STRUCTURE_OPERATIONAL_SCOPE_WRAPPER_ID,
    STRUCTURE_ROOT_ID,
    STRUCTURE_SUBCOMPONENTS_CONTAINER_ID,
    STRUCTURE_VALIDATION_MESSAGE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    SUBCOMPONENT_DELETE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_OWNER_TYPE,
    SUBCOMPONENT_ROW_TYPE,
    row_id,
)


def build_tool_structure_editor(
    *,
    configuration_document: Mapping[str, object] | None = None,
) -> Component:
    configuration = (
        ToolConfiguration.from_document(configuration_document)
        if configuration_document is not None
        else None
    )
    component_rows, subcomponent_rows, operational_scope = (
        structure_editor_table_data_from_configuration(configuration)
        if configuration is not None
        else ([], [], None)
    )
    structure = configuration.structure if configuration is not None else None
    kind = configuration.kind if configuration is not None else None
    component_options = _component_options(component_rows)
    return html.Section(
        [
            dcc.Store(
                id=STRUCTURE_DOCUMENT_STORE_ID,
                data=structure.to_document() if structure is not None else None,
                storage_type='memory',
            ),
            dcc.Store(
                id=STRUCTURE_VALIDITY_STORE_ID,
                data=structure is not None,
                storage_type='memory',
            ),
            _heading(kind),
            html.Label(
                [
                    html.Span('Ámbito operacional'),
                    dcc.Dropdown(
                        id=STRUCTURE_OPERATIONAL_SCOPE_ID,
                        options=[
                            {'label': scope.value.capitalize(), 'value': scope.value}
                            for scope in ToolScope
                        ],
                        value=operational_scope,
                        clearable=False,
                    ),
                ],
                id=STRUCTURE_OPERATIONAL_SCOPE_WRAPPER_ID,
                hidden=kind is not ToolConfigurationKind.PROCESS,
                className='ada-tool-structure-editor__scope',
            ),
            _collection_section(
                title='Components',
                copy=(
                    'Define los bloques principales de presentación de la Tool. '
                    'El orden visual se conserva en la configuración.'
                ),
                add_label='Agregar componente',
                add_id=STRUCTURE_ADD_COMPONENT_ID,
                container_id=STRUCTURE_COMPONENTS_CONTAINER_ID,
                children=[
                    build_component_editor_row(
                        index=index,
                        row=row,
                        kind=kind,
                    )
                    for index, row in enumerate(component_rows)
                ],
            ),
            _collection_section(
                title='Subcomponents',
                copy=(
                    'Define los elementos internos y sus relaciones visibles '
                    'dentro de cada Component.'
                ),
                add_label='Agregar subcomponente',
                add_id=STRUCTURE_ADD_SUBCOMPONENT_ID,
                container_id=STRUCTURE_SUBCOMPONENTS_CONTAINER_ID,
                children=[
                    build_subcomponent_editor_row(
                        index=index,
                        row=row,
                        kind=kind,
                        component_options=component_options,
                    )
                    for index, row in enumerate(subcomponent_rows)
                ],
            ),
            html.Div(
                id=STRUCTURE_VALIDATION_MESSAGE_ID,
                role='status',
                className='ada-tool-structure-editor__validation',
            ),
            html.Div(
                [
                    html.Small('Destinos KPI derivados'),
                    html.Strong(
                        ', '.join(structure.kpi_destination_keys) if structure is not None else '—',
                        id=STRUCTURE_KPI_DESTINATIONS_ID,
                    ),
                ],
                className='ada-tool-structure-editor__destinations',
            ),
        ],
        id=STRUCTURE_ROOT_ID,
        className='ada-tool-structure-editor',
        **{'data-ada-tool-structure-editor': 'true'},
    )


def build_component_editor_row(
    *,
    index: int,
    row: Mapping[str, object] | None,
    kind: ToolConfigurationKind | None,
) -> Component:
    values = row or {}
    fields: list[Component] = [
        _text_field(
            label='Key',
            component_id=row_id(COMPONENT_KEY_TYPE, index),
            value=values.get('key'),
            placeholder='component_key',
        ),
        _text_field(
            label='Nombre',
            component_id=row_id(COMPONENT_DISPLAY_NAME_TYPE, index),
            value=values.get('display_name'),
            placeholder='Nombre del component',
        ),
    ]
    if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        fields.append(
            _dropdown_field(
                label='Scope',
                component_id=row_id(COMPONENT_SCOPE_TYPE, index),
                value=values.get('scope'),
                options=[
                    {'label': scope.value.capitalize(), 'value': scope.value} for scope in ToolScope
                ],
            )
        )
    if kind is ToolConfigurationKind.PROCESS:
        fields.append(
            _dropdown_field(
                label='Layout',
                component_id=row_id(COMPONENT_LAYOUT_ROLE_TYPE, index),
                value=values.get('layout_role'),
                options=[
                    {'label': role.value.capitalize(), 'value': role.value}
                    for role in ProcessLayoutRole
                ],
            )
        )
    return html.Article(
        [
            html.Div(
                fields,
                className='ada-tool-structure-editor__row-fields',
            ),
            html.Button(
                'Eliminar',
                id=row_id(COMPONENT_DELETE_TYPE, index),
                type='button',
                n_clicks=0,
                className='ada-tool-structure-editor__delete',
            ),
        ],
        id=row_id(COMPONENT_ROW_TYPE, index),
        className='ada-tool-structure-editor__row',
        **{'data-structure-row': 'component'},
    )


def build_subcomponent_editor_row(
    *,
    index: int,
    row: Mapping[str, object] | None,
    kind: ToolConfigurationKind | None,
    component_options: Sequence[Mapping[str, str]],
) -> Component:
    values = row or {}
    fields: list[Component] = [
        _dropdown_field(
            label='Component',
            component_id=row_id(SUBCOMPONENT_OWNER_TYPE, index),
            value=values.get('owner_component_key'),
            options=component_options,
        ),
        _text_field(
            label='Key',
            component_id=row_id(SUBCOMPONENT_KEY_TYPE, index),
            value=values.get('key'),
            placeholder='subcomponent_key',
        ),
        _text_field(
            label='Nombre',
            component_id=row_id(SUBCOMPONENT_DISPLAY_NAME_TYPE, index),
            value=values.get('display_name'),
            placeholder='Nombre del subcomponent',
        ),
    ]
    if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        fields.append(
            _dropdown_field(
                label='Linked Components',
                component_id=row_id(SUBCOMPONENT_LINKED_TYPE, index),
                value=_linked_values(values.get('linked_component_keys')),
                options=component_options,
                multi=True,
            )
        )
    return html.Article(
        [
            html.Div(
                fields,
                className='ada-tool-structure-editor__row-fields',
            ),
            html.Button(
                'Eliminar',
                id=row_id(SUBCOMPONENT_DELETE_TYPE, index),
                type='button',
                n_clicks=0,
                className='ada-tool-structure-editor__delete',
            ),
        ],
        id=row_id(SUBCOMPONENT_ROW_TYPE, index),
        className='ada-tool-structure-editor__row',
        **{'data-structure-row': 'subcomponent'},
    )


def _heading(kind: ToolConfigurationKind | None) -> Component:
    return html.Div(
        [
            html.H3('Estructura', className='ada-tool-structure-editor__title'),
            html.P(
                (
                    'Components y Subcomponents construyen la capa de presentación de esta Tool. '
                    'Las reglas estructurales permanecen en el dominio.'
                ),
                className='ada-tool-structure-editor__copy',
            ),
            html.Div(
                _kind_label(kind),
                id=STRUCTURE_KIND_ID,
                className='ada-tool-structure-editor__kind',
            ),
        ],
        className='ada-tool-structure-editor__heading',
    )


def _collection_section(
    *,
    title: str,
    copy: str,
    add_label: str,
    add_id: str,
    container_id: str,
    children: list[Component],
) -> Component:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H4(title),
                            html.P(copy),
                        ],
                        className='ada-tool-structure-editor__collection-copy',
                    ),
                    html.Button(
                        add_label,
                        id=add_id,
                        type='button',
                        n_clicks=0,
                        className='ada-tool-structure-editor__add',
                    ),
                ],
                className='ada-tool-structure-editor__collection-heading',
            ),
            html.Div(
                children,
                id=container_id,
                className='ada-tool-structure-editor__rows',
            ),
        ],
        className='ada-tool-structure-editor__collection',
    )


def _text_field(
    *,
    label: str,
    component_id: object,
    value: object,
    placeholder: str,
) -> Component:
    return html.Label(
        [
            html.Span(label),
            dcc.Input(
                id=component_id,
                value=value,
                type='text',
                placeholder=placeholder,
                debounce=True,
            ),
        ],
        className='ada-tool-structure-editor__field',
    )


def _dropdown_field(
    *,
    label: str,
    component_id: object,
    value: object,
    options: Sequence[Mapping[str, str]],
    multi: bool = False,
) -> Component:
    return html.Label(
        [
            html.Span(label),
            dcc.Dropdown(
                id=component_id,
                value=value,
                options=list(options),
                multi=multi,
                clearable=multi,
            ),
        ],
        className='ada-tool-structure-editor__field',
    )


def _component_options(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for row in rows:
        key = str(row.get('key') or '').strip()
        if not key:
            continue
        display_name = str(row.get('display_name') or '').strip()
        options.append(
            {
                'label': display_name or key,
                'value': key,
            }
        )
    return options


def _linked_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _kind_label(kind: ToolConfigurationKind | None) -> str:
    if kind is ToolConfigurationKind.PROCESS:
        return 'Process'
    if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        return 'Integrated Operations'
    return 'Sin configuración'
