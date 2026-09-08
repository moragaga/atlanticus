# Espejo comentado de la presentación estructural anidada.

from __future__ import annotations

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
    COMPONENT_ADD_SUBCOMPONENT_TYPE,
    COMPONENT_DELETE_TYPE,
    COMPONENT_DISPLAY_NAME_TYPE,
    COMPONENT_KEY_TYPE,
    COMPONENT_LAYOUT_ROLE_TYPE,
    COMPONENT_LAYOUT_WRAPPER_TYPE,
    COMPONENT_ROW_TYPE,
    COMPONENT_SCOPE_TYPE,
    COMPONENT_SCOPE_WRAPPER_TYPE,
    COMPONENT_SUBCOMPONENTS_CONTAINER_TYPE,
    STRUCTURE_ADD_COMPONENT_ID,
    STRUCTURE_COMPONENTS_CONTAINER_ID,
    STRUCTURE_DOCUMENT_STORE_ID,
    STRUCTURE_ROOT_ID,
    STRUCTURE_VALIDATION_MESSAGE_ID,
    STRUCTURE_VALIDITY_STORE_ID,
    SUBCOMPONENT_DELETE_TYPE,
    SUBCOMPONENT_DISPLAY_NAME_TYPE,
    SUBCOMPONENT_KEY_TYPE,
    SUBCOMPONENT_LINKED_TYPE,
    SUBCOMPONENT_LINKED_WRAPPER_TYPE,
    SUBCOMPONENT_ROW_TYPE,
    component_nested_id,
    nested_row_id,
    row_id,
)

_COVERAGE_MINE_PLANT = 'mine_plant'


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
                data=structure.to_document() if structure is not None else None,
                storage_type='memory',
            ),
            dcc.Store(
                id=STRUCTURE_VALIDITY_STORE_ID,
                data=structure is not None,
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
                            'Cada componente contiene sus subcomponentes. '
                            'En Operaciones integradas, un subcomponente '
                            'puede ser visible también en otros componentes '
                            'compatibles.'
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
                                            'La estructura se configura en '
                                            'conjunto: componente, '
                                            'subcomponentes y relaciones de '
                                            'visibilidad.'
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


# Cada Component contiene visualmente sus Subcomponents.
def build_component_editor_row(
    *,
    index: int,
    row: Mapping[str, object] | None,
    kind: ToolConfigurationKind | None,
    coverage: str | None,
    subcomponent_rows: Sequence[tuple[int, Mapping[str, object]]] = (),
    all_component_rows: Sequence[Mapping[str, object]] = (),
) -> Component:
    values = row or {}
    scope_hidden = not (
        kind is ToolConfigurationKind.INTEGRATED_OPERATIONS
        and coverage == _COVERAGE_MINE_PLANT
    )
    layout_hidden = kind is not ToolConfigurationKind.PROCESS
    linked_hidden = kind is not ToolConfigurationKind.INTEGRATED_OPERATIONS
    owner_key = str(values.get('key') or '').strip()
    linked_options = _linked_component_options(
        all_component_rows,
        owner_index=index,
        coverage=coverage,
    )
    return html.Article(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(
                                str(values.get('display_name') or '').strip()
                                or f'Componente {index + 1}'
                            ),
                            html.Small('Componente'),
                        ],
                        className='ada-tool-structure-editor__component-title',
                    ),
                    html.Button(
                        'Eliminar',
                        id=row_id(COMPONENT_DELETE_TYPE, index),
                        type='button',
                        n_clicks=0,
                        className=(
                            'btn btn-outline-danger btn-sm '
                            'ada-tool-structure-editor__delete'
                        ),
                    ),
                ],
                className='ada-tool-structure-editor__component-head',
            ),
            html.Div(
                [
                    _text_field(
                        label='Identificador',
                        component_id=row_id(COMPONENT_KEY_TYPE, index),
                        value=values.get('key'),
                        placeholder='component_key',
                    ),
                    _text_field(
                        label='Nombre',
                        component_id=row_id(COMPONENT_DISPLAY_NAME_TYPE, index),
                        value=values.get('display_name'),
                        placeholder='Nombre del componente',
                    ),
                    html.Div(
                        _dropdown_field(
                            label='Ámbito',
                            component_id=row_id(COMPONENT_SCOPE_TYPE, index),
                            value=values.get('scope'),
                            options=[
                                {'label': 'Mina', 'value': ToolScope.MINE.value},
                                {'label': 'Planta', 'value': ToolScope.PLANT.value},
                            ],
                        ),
                        id=row_id(COMPONENT_SCOPE_WRAPPER_TYPE, index),
                        hidden=scope_hidden,
                        className='ada-tool-structure-editor__context-field',
                    ),
                    html.Div(
                        _dropdown_field(
                            label='Posición',
                            component_id=row_id(COMPONENT_LAYOUT_ROLE_TYPE, index),
                            value=values.get('layout_role'),
                            options=[
                                {
                                    'label': 'Izquierda',
                                    'value': ProcessLayoutRole.LEFT.value,
                                },
                                {
                                    'label': 'Centro',
                                    'value': ProcessLayoutRole.CENTER.value,
                                },
                                {
                                    'label': 'Derecha',
                                    'value': ProcessLayoutRole.RIGHT.value,
                                },
                                {
                                    'label': 'Inferior',
                                    'value': ProcessLayoutRole.BOTTOM.value,
                                },
                            ],
                        ),
                        id=row_id(COMPONENT_LAYOUT_WRAPPER_TYPE, index),
                        hidden=layout_hidden,
                        className='ada-tool-structure-editor__context-field',
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
                                            'Pertenecen a este componente. '
                                            'La relación "Visible también en" '
                                            'no duplica el subcomponente.'
                                        )
                                    ),
                                ],
                                className=(
                                    'ada-tool-structure-editor__subcomponents-copy'
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
                                    'ada-tool-structure-editor__add-subcomponent'
                                ),
                            ),
                        ],
                        className=(
                            'ada-tool-structure-editor__subcomponents-heading'
                        ),
                    ),
                    html.Div(
                        [
                            build_subcomponent_editor_row(
                                index=subcomponent_index,
                                owner_index=index,
                                row=subcomponent_row,
                                linked_hidden=linked_hidden,
                                linked_component_options=linked_options,
                            )
                            for subcomponent_index, subcomponent_row in subcomponent_rows
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
                **{'data-owner-component-key': owner_key},
            ),
        ],
        id=row_id(COMPONENT_ROW_TYPE, index),
        className='ada-tool-structure-editor__component-card',
        **{'data-structure-row': 'component'},
    )


# Visible también en representa linked_component_keys sin duplicar ownership.
def build_subcomponent_editor_row(
    *,
    index: int,
    owner_index: int,
    row: Mapping[str, object] | None,
    linked_hidden: bool,
    linked_component_options: Sequence[Mapping[str, str]] = (),
) -> Component:
    values = row or {}
    return html.Article(
        [
            html.Div(
                [
                    _text_field(
                        label='Identificador',
                        component_id=nested_row_id(
                            SUBCOMPONENT_KEY_TYPE,
                            index,
                            owner_index,
                        ),
                        value=values.get('key'),
                        placeholder='subcomponent_key',
                    ),
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
                            value=_linked_values(
                                values.get('linked_component_keys')
                            ),
                            options=linked_component_options,
                            multi=True,
                            placeholder='Seleccionar componentes compatibles',
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
                className='ada-tool-structure-editor__row-fields',
            ),
            html.Button(
                'Eliminar',
                id=nested_row_id(
                    SUBCOMPONENT_DELETE_TYPE,
                    index,
                    owner_index,
                ),
                type='button',
                n_clicks=0,
                className=(
                    'btn btn-outline-danger btn-sm '
                    'ada-tool-structure-editor__delete'
                ),
            ),
        ],
        id=nested_row_id(SUBCOMPONENT_ROW_TYPE, index, owner_index),
        className='ada-tool-structure-editor__subcomponent-row',
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
                className='form-control ada-tool-structure-editor__text-input',
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
    coverage: str | None,
) -> list[dict[str, str]]:
    if owner_index < 0 or owner_index >= len(rows):
        return []
    owner_scope = _effective_scope(rows[owner_index], coverage=coverage)
    if not owner_scope:
        return []
    options: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if index == owner_index:
            continue
        if _effective_scope(row, coverage=coverage) != owner_scope:
            continue
        key = str(row.get('key') or '').strip()
        if not key:
            continue
        display_name = str(row.get('display_name') or '').strip()
        options.append({'label': display_name or key, 'value': key})
    return options


def _effective_scope(
    row: Mapping[str, object],
    *,
    coverage: str | None,
) -> str:
    if coverage in {'mine', 'plant'}:
        return coverage
    return str(row.get('scope') or '').strip()


def _subcomponent_rows_by_owner(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, list[tuple[int, Mapping[str, object]]]]:
    resolved: dict[str, list[tuple[int, Mapping[str, object]]]] = {}
    for index, row in enumerate(rows):
        owner_key = str(row.get('owner_component_key') or '').strip()
        resolved.setdefault(owner_key, []).append((index, row))
    return resolved


def _linked_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dash_select_style() -> dict[str, str]:
    return {
        '--Dash-Spacing': '4px',
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-secondary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-secondary)',
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
