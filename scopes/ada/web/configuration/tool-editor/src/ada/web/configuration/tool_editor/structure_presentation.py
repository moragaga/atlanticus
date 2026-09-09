from __future__ import annotations

from collections.abc import Mapping, Sequence

from dash import dcc, html
from dash.development.base_component import Component

from ada.configuration.tools import (
    ToolConfiguration,
    ToolConfigurationKind,
    ToolScope,
)
from ada.web.configuration.tool_editor.structure import (
    structure_editor_table_data_from_configuration,
)
from ada.web.configuration.tool_editor.structure_ids import (
    COMPONENT_ADD_SUBCOMPONENT_TYPE,
    COMPONENT_DELETE_TYPE,
    COMPONENT_DISPLAY_NAME_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_ROW_TYPE,
    COMPONENT_SCOPE_TYPE,
    COMPONENT_SCOPE_WRAPPER_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    COMPONENT_SUMMARY_COUNT_TYPE,
    COMPONENT_SUMMARY_NAME_TYPE,
    COMPONENT_SUMMARY_SCOPE_TYPE,
    STRUCTURE_ADD_COMPONENT_ID,
    STRUCTURE_COMPONENTS_CONTAINER_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_KIND_STORE_ID,
    STRUCTURE_ROOT_ID,
    STRUCTURE_VALIDATION_MESSAGE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    SUBCOMPONENT_DELETE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_LINKED_WRAPPER_TYPE,
    SUBCOMPONENT_ROW_TYPE,
    SUBCOMPONENT_SUMMARY_LINK_TYPE,
    SUBCOMPONENT_SUMMARY_NAME_TYPE,
    component_nested_id,
    nested_row_id,
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
    component_rows, subcomponent_rows, coverage = (
        structure_editor_table_data_from_configuration(configuration)
        if configuration is not None
        else ([], [], None)
    )
    structure = configuration.structure if configuration is not None else None
    kind = configuration.kind if configuration is not None else None
    nested_rows = _subcomponent_rows_by_owner(subcomponent_rows)

    return html.Section(
        [
            dcc.Store(
                id=STRUCTURE_DOCUMENT_STORE_ID,
                data=(
                    structure.to_document()
                    if structure is not None
                    else None
                ),
                storage_type='memory',
            ),
            dcc.Store(
                id=STRUCTURE_VALIDITY_STORE_ID,
                data=structure is not None,
                storage_type='memory',
            ),
            dcc.Store(
                id=STRUCTURE_KIND_STORE_ID,
                data=kind.value if kind is not None else None,
                storage_type='memory',
            ),
            html.Div(
                [
                    html.H3(
                        'Estructura',
                        className='ada-tool-structure-editor__title',
                    ),
                    html.P(
                        (
                            'Los componentes se muestran como un resumen '
                            'compacto. Cada uno contiene sus subcomponentes '
                            'y puede editarse sin exponer identificadores '
                            'internos.'
                        ),
                        className='ada-tool-structure-editor__copy',
                    ),
                ],
                className='ada-tool-structure-editor__heading',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H4('Componentes'),
                                    html.P(
                                        (
                                            'Agrega los bloques de la '
                                            'herramienta. La paginación se '
                                            'podrá aplicar sobre esta lista '
                                            'de resumen.'
                                        )
                                    ),
                                ],
                                className=(
                                    'ada-tool-structure-editor__collection-copy'
                                ),
                            ),
                            html.Button(
                                'Agregar componente',
                                id=STRUCTURE_ADD_COMPONENT_ID,
                                type='button',
                                n_clicks=0,
                                className=(
                                    'btn btn-outline-secondary '
                                    'ada-tool-structure-editor__add'
                                ),
                            ),
                        ],
                        className=(
                            'ada-tool-structure-editor__collection-heading'
                        ),
                    ),
                    html.Div(
                        [
                            build_component_editor_row(
                                index=index,
                                row=row,
                                kind=kind,
                                coverage=coverage,
                                subcomponent_rows=nested_rows.get(
                                    str(row.get('key') or ''),
                                    (),
                                ),
                                all_component_rows=component_rows,
                            )
                            for index, row in enumerate(component_rows)
                        ],
                        id=STRUCTURE_COMPONENTS_CONTAINER_ID,
                        className='ada-tool-structure-editor__components',
                    ),
                ],
                className='ada-tool-structure-editor__collection',
            ),
            html.Div(
                id=STRUCTURE_VALIDATION_MESSAGE_ID,
                role='status',
                className='ada-tool-structure-editor__validation',
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
    coverage: str | None,
    subcomponent_rows: Sequence[
        tuple[int, Mapping[str, object]]
    ] = (),
    all_component_rows: Sequence[Mapping[str, object]] = (),
) -> Component:
    values = row or {}
    integrated = (
        kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
    )
    process = kind is ToolConfigurationKind.PROCESS
    scope_value = coverage if process else values.get('scope')
    linked_options = _linked_component_options(
        all_component_rows,
        owner_index=index,
    )

    return html.Details(
        [
            html.Summary(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Strong(
                                        (
                                            str(
                                                values.get(
                                                    'display_name'
                                                )
                                                or ''
                                            ).strip()
                                            or 'Nuevo componente'
                                        ),
                                        id=row_id(
                                            COMPONENT_SUMMARY_NAME_TYPE,
                                            index,
                                        ),
                                    ),
                                    html.Span(
                                        _summary_scope(
                                            kind=kind,
                                            coverage=coverage,
                                            scope=values.get('scope'),
                                        ),
                                        id=row_id(
                                            COMPONENT_SUMMARY_SCOPE_TYPE,
                                            index,
                                        ),
                                    ),
                                ],
                                className=(
                                    'ada-tool-structure-editor__summary-copy'
                                ),
                            ),
                        ],
                        className=(
                            'ada-tool-structure-editor__summary-main'
                        ),
                    ),
                    html.Div(
                        [
                            html.Span(
                                _subcomponent_count_label(
                                    len(subcomponent_rows)
                                ),
                                id=row_id(
                                    COMPONENT_SUMMARY_COUNT_TYPE,
                                    index,
                                ),
                                className=(
                                    'ada-tool-structure-editor__summary-meta'
                                ),
                            ),
                            html.Span(
                                'Editar',
                                className=(
                                    'ada-tool-structure-editor__summary-action'
                                ),
                            ),
                        ],
                        className=(
                            'ada-tool-structure-editor__summary-actions'
                        ),
                    ),
                ],
                className='ada-tool-structure-editor__component-summary',
            ),
            dcc.Store(
                id=row_id(COMPONENT_KEY_TYPE, index),
                data=values.get('key'),
                storage_type='memory',
            ),
            html.Div(
                [
                    _text_field(
                        label='Nombre',
                        component_id=row_id(
                            COMPONENT_DISPLAY_NAME_TYPE,
                            index,
                        ),
                        value=values.get('display_name'),
                        placeholder='Nombre del componente',
                    ),
                    html.Div(
                        _dropdown_field(
                            label='Ámbito',
                            component_id=row_id(
                                COMPONENT_SCOPE_TYPE,
                                index,
                            ),
                            value=scope_value,
                            options=[
                                {
                                    'label': 'Mina',
                                    'value': ToolScope.MINE.value,
                                },
                                {
                                    'label': 'Planta',
                                    'value': ToolScope.PLANT.value,
                                },
                            ],
                            disabled=not integrated,
                        ),
                        id=row_id(
                            COMPONENT_SCOPE_WRAPPER_TYPE,
                            index,
                        ),
                        hidden=kind is None,
                        className=(
                            'ada-tool-structure-editor__context-field'
                        ),
                    ),
                ],
                className='ada-tool-structure-editor__row-fields',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Strong('Subcomponentes'),
                                    html.Small(
                                        (
                                            'Cada subcomponente tiene un '
                                            'único propietario. En '
                                            'Operaciones integradas puede '
                                            'ser visible en otros '
                                            'componentes compatibles.'
                                        )
                                    ),
                                ],
                                className=(
                                    'ada-tool-structure-editor__'
                                    'subcomponents-copy'
                                ),
                            ),
                            html.Button(
                                'Agregar subcomponente',
                                id=component_nested_id(
                                    COMPONENT_ADD_SUBCOMPONENT_TYPE,
                                    index,
                                ),
                                type='button',
                                n_clicks=0,
                                className=(
                                    'btn btn-outline-secondary btn-sm '
                                    'ada-tool-structure-editor__'
                                    'add-subcomponent'
                                ),
                            ),
                        ],
                        className=(
                            'ada-tool-structure-editor__'
                            'subcomponents-heading'
                        ),
                    ),
                    html.Div(
                        [
                            build_subcomponent_editor_row(
                                index=sub_index,
                                owner_index=index,
                                row=sub_row,
                                linked_hidden=not integrated,
                                linked_component_options=linked_options,
                            )
                            for sub_index, sub_row in subcomponent_rows
                        ],
                        id=component_nested_id(
                            COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
                            index,
                        ),
                        className=(
                            'ada-tool-structure-editor__subcomponents-rows'
                        ),
                    ),
                ],
                className='ada-tool-structure-editor__subcomponents',
            ),
            html.Div(
                html.Button(
                    'Eliminar componente',
                    id=row_id(COMPONENT_DELETE_TYPE, index),
                    type='button',
                    n_clicks=0,
                    className='btn btn-outline-danger btn-sm',
                ),
                className='ada-tool-structure-editor__destructive-actions',
            ),
        ],
        id=row_id(COMPONENT_ROW_TYPE, index),
        className='ada-tool-structure-editor__component-card',
        open=False,
        **{'data-structure-row': 'component'},
    )


def build_subcomponent_editor_row(
    *,
    index: int,
    owner_index: int,
    row: Mapping[str, object] | None,
    linked_hidden: bool,
    linked_component_options: Sequence[Mapping[str, str]] = (),
) -> Component:
    values = row or {}
    linked_values = _linked_values(
        values.get('linked_component_keys')
    )
    return html.Details(
        [
            html.Summary(
                [
                    html.Div(
                        [
                            html.Strong(
                                (
                                    str(
                                        values.get('display_name')
                                        or ''
                                    ).strip()
                                    or 'Nuevo subcomponente'
                                ),
                                id=nested_row_id(
                                    SUBCOMPONENT_SUMMARY_NAME_TYPE,
                                    index,
                                    owner_index,
                                ),
                            ),
                            html.Span(
                                _shared_label(linked_values),
                                id=nested_row_id(
                                    SUBCOMPONENT_SUMMARY_LINK_TYPE,
                                    index,
                                    owner_index,
                                ),
                                className=(
                                    'ada-tool-structure-editor__summary-meta'
                                ),
                            ),
                        ],
                        className='ada-tool-structure-editor__summary-copy',
                    ),
                    html.Span(
                        'Editar',
                        className='ada-tool-structure-editor__summary-action',
                    ),
                ],
                className='ada-tool-structure-editor__subcomponent-summary',
            ),
            dcc.Store(
                id=nested_row_id(
                    SUBCOMPONENT_KEY_TYPE,
                    index,
                    owner_index,
                ),
                data=values.get('key'),
                storage_type='memory',
            ),
            html.Div(
                [
                    _text_field(
                        label='Nombre',
                        component_id=nested_row_id(
                            SUBCOMPONENT_DISPLAY_NAME_TYPE,
                            index,
                            owner_index,
                        ),
                        value=values.get('display_name'),
                        placeholder='Nombre del subcomponente',
                    ),
                    html.Div(
                        _dropdown_field(
                            label='Visible también en',
                            component_id=nested_row_id(
                                SUBCOMPONENT_LINKED_TYPE,
                                index,
                                owner_index,
                            ),
                            value=linked_values,
                            options=linked_component_options,
                            multi=True,
                            placeholder=(
                                'Seleccionar componentes compatibles'
                            ),
                            disabled=(
                                linked_hidden
                                or not linked_component_options
                            ),
                        ),
                        id=nested_row_id(
                            SUBCOMPONENT_LINKED_WRAPPER_TYPE,
                            index,
                            owner_index,
                        ),
                        hidden=linked_hidden,
                        className='ada-tool-structure-editor__context-field',
                    ),
                ],
                className='ada-tool-structure-editor__subcomponent-fields',
            ),
            html.Div(
                html.Button(
                    'Eliminar subcomponente',
                    id=nested_row_id(
                        SUBCOMPONENT_DELETE_TYPE,
                        index,
                        owner_index,
                    ),
                    type='button',
                    n_clicks=0,
                    className='btn btn-outline-danger btn-sm',
                ),
                className='ada-tool-structure-editor__destructive-actions',
            ),
        ],
        id=nested_row_id(
            SUBCOMPONENT_ROW_TYPE,
            index,
            owner_index,
        ),
        className='ada-tool-structure-editor__subcomponent-row',
        open=False,
        **{'data-structure-row': 'subcomponent'},
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
                className='ada-tool-structure-editor__text-input',
                style=_dash_input_style(),
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
    placeholder: str | None = None,
    disabled: bool = False,
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
                placeholder=placeholder,
                disabled=disabled,
                className='ada-tool-structure-editor__select',
                style=_dash_select_style(),
            ),
        ],
        className='ada-tool-structure-editor__field',
    )


def _linked_component_options(
    rows: Sequence[Mapping[str, object]],
    *,
    owner_index: int,
) -> list[dict[str, str]]:
    if owner_index < 0 or owner_index >= len(rows):
        return []
    owner_scope = str(
        rows[owner_index].get('scope') or ''
    ).strip()
    if not owner_scope:
        return []
    options: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if index == owner_index:
            continue
        if str(row.get('scope') or '').strip() != owner_scope:
            continue
        key = str(row.get('key') or '').strip()
        if not key:
            continue
        display_name = str(
            row.get('display_name') or ''
        ).strip()
        options.append(
            {
                'label': display_name or key,
                'value': key,
            }
        )
    return options


def _subcomponent_rows_by_owner(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, list[tuple[int, Mapping[str, object]]]]:
    resolved: dict[
        str,
        list[tuple[int, Mapping[str, object]]],
    ] = {}
    for index, row in enumerate(rows):
        owner_key = str(
            row.get('owner_component_key') or ''
        ).strip()
        resolved.setdefault(owner_key, []).append((index, row))
    return resolved


def _linked_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [
            item.strip()
            for item in value.split(',')
            if item.strip()
        ]
    if isinstance(value, (list, tuple)):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]
    return []


def _summary_scope(
    *,
    kind: ToolConfigurationKind | None,
    coverage: str | None,
    scope: object,
) -> str:
    if kind is ToolConfigurationKind.PROCESS:
        if coverage == 'mine':
            return 'Mina'
        if coverage == 'plant':
            return 'Planta'
        return 'Definir ámbito'
    if kind is ToolConfigurationKind.INTEGRATED_OPERATIONS:
        if scope == ToolScope.MINE.value:
            return 'Mina'
        if scope == ToolScope.PLANT.value:
            return 'Planta'
        return 'Definir ámbito'
    return 'Sin tipo'


def _subcomponent_count_label(count: int) -> str:
    if count == 1:
        return '1 subcomponente'
    return f'{count} subcomponentes'


def _shared_label(linked_values: Sequence[str]) -> str:
    count = len(linked_values)
    if count == 0:
        return 'Sin compartir'
    if count == 1:
        return 'Compartido con 1 componente'
    return f'Compartido con {count} componentes'


def _dash_input_style() -> dict[str, str]:
    return {
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Fill-Interactive-Weak': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Inverse-Strong': 'var(--atlanticus-ui-surface)',
        '--Dash-Text-Primary': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Strong': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Weak': 'var(--atlanticus-ui-text-muted)',
        '--Dash-Text-Disabled': 'var(--atlanticus-ui-text-soft)',
        '--Dash-Fill-Primary-Hover': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Primary-Active': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Disabled': 'var(--atlanticus-ui-border)',
        '--Dash-Shading-Strong': 'rgb(7 21 34 / 25%)',
        '--Dash-Shading-Weak': 'rgb(7 21 34 / 12%)',
    }


def _dash_select_style() -> dict[str, str]:
    return {
        '--Dash-Spacing': '4px',
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Fill-Interactive-Weak': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Inverse-Strong': 'var(--atlanticus-ui-surface)',
        '--Dash-Text-Primary': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Strong': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Weak': 'var(--atlanticus-ui-text-muted)',
        '--Dash-Text-Disabled': 'var(--atlanticus-ui-text-soft)',
        '--Dash-Fill-Primary-Hover': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Primary-Active': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Disabled': 'var(--atlanticus-ui-border)',
        '--Dash-Shading-Strong': 'rgb(7 21 34 / 25%)',
        '--Dash-Shading-Weak': 'rgb(7 21 34 / 12%)',
    }
