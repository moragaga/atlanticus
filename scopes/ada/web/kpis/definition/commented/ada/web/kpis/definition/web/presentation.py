# Espejo comentado de la superficie Web de KPI Definition.
from __future__ import annotations

from collections.abc import Mapping

import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.development.base_component import Component

from ada.web.configuration import (
    ConfigurationPage,
    build_configuration_pagination,
    configuration_dash_select_style,
)
from ada.web.kpis.definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
)
from ada.web.kpis.definition.web.ids import (
    DEPENDENCY_ID,
    EDITOR_BACKDROP_ID,
    EDITOR_CANCEL_ID,
    EDITOR_CLOSE_ID,
    EDITOR_DETAIL_ID,
    EDITOR_FORM_ID,
    EDITOR_KPI_KEY_ID,
    EDITOR_MODAL_ID,
    EDITOR_RESULT_ID,
    EDITOR_SAVE_ID,
    EDITOR_TITLE_ID,
    EDITOR_VIEW_ID,
    GRID_CONTAINER_ID,
    PAGINATION_CONTAINER_ID,
    PAGINATION_PREFIX,
    ROOT_ID,
    SEARCH_ID,
    STATUS_FILTER_ID,
    TABLE_BODY_ID,
    row_add_id,
    row_delete_id,
    row_edit_id,
    row_view_id,
)
from ada.web.kpis.definition.web.query import (
    KpiDefinitionEditorItem,
    KpiDefinitionEditorStatus,
    KpiDefinitionQuery,
    KpiDefinitionStatusFilter,
)

_MODAL_CLOSED = 'ada-kpi-definition__modal'
_MODAL_OPEN = 'ada-kpi-definition__modal ada-kpi-definition__modal--open'


def build_kpi_definition_editor(
    page: ConfigurationPage[KpiDefinitionEditorItem],
    *,
    query: KpiDefinitionQuery,
    authority: KpiDefinitionAuthorityCatalog | None,
    can_manage: bool = True,
) -> Component:
    dependency_reason = (
        'La proyección de Configuración KPI no está disponible.'
        if authority is None
        else None
    )
    return html.Div(
        [
            _toolbar(query, authority=authority),
            html.Div(
                _dependency_content(dependency_reason),
                id=DEPENDENCY_ID,
                hidden=dependency_reason is None,
                className='ada-kpi-definition__dependency',
            ),
            html.Div(
                build_kpi_definition_grid(
                    page,
                    query=query,
                    authority=authority,
                    can_manage=can_manage,
                ),
                id=GRID_CONTAINER_ID,
            ),
            html.Div(
                build_configuration_pagination(page, id_prefix=PAGINATION_PREFIX),
                id=PAGINATION_CONTAINER_ID,
            ),
            build_kpi_definition_modal(),
        ],
        id=ROOT_ID,
        className='ada-kpi-definition',
    )


def build_kpi_definition_grid(
    page: ConfigurationPage[KpiDefinitionEditorItem],
    *,
    query: KpiDefinitionQuery,
    authority: KpiDefinitionAuthorityCatalog | None,
    can_manage: bool = True,
) -> Component:
    rows = [_row(item, can_manage=can_manage) for item in page.items]
    empty_state: Component | None = None
    empty_reason: str | None = None

    if not page.items:
        if authority is None:
            empty_reason = 'dependency'
            empty_state = _empty_state(
                icon='!',
                title='Configuración KPI no disponible.',
                detail='Las definiciones se habilitan cuando la proyección de KPI está disponible.',
                reason=empty_reason,
            )
        elif query.search or query.status is not KpiDefinitionStatusFilter.ALL:
            empty_reason = 'filtered'
            empty_state = _empty_state(
                icon='⌕',
                title='No se encontraron KPI.',
                detail='Ajusta o limpia los filtros para volver a mostrar resultados.',
                reason=empty_reason,
            )
        elif not authority.kpi_keys:
            empty_reason = 'no-kpis'
            empty_state = _empty_state(
                icon='+',
                title='Todavía no hay KPI configurados.',
                detail='Crea al menos un KPI en Configuración KPI antes de definir información descriptiva.',
                reason=empty_reason,
            )

        if empty_state is not None:
            rows.append(_empty_row(empty_reason or 'empty'))

    placeholder_count = page.request.page_size - len(rows)
    rows.extend(_placeholder_row(index) for index in range(max(0, placeholder_count)))

    shell_class = 'ada-kpi-definition__table-shell'
    if empty_state is not None:
        shell_class += ' ada-kpi-definition__table-shell--empty'

    return html.Div(
        [
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th('KPI'),
                                html.Th('Estado'),
                                html.Th(
                                    'Acciones',
                                    className='ada-kpi-definition__actions-heading',
                                ),
                            ]
                        )
                    ),
                    html.Tbody(
                        rows,
                        id=TABLE_BODY_ID,
                        **{
                            'data-page-size': str(page.request.page_size),
                            'data-empty-reason': empty_reason or 'none',
                        },
                    ),
                ],
                className='ada-kpi-definition__table',
            ),
            empty_state,
        ],
        className=shell_class,
    )


def build_kpi_definition_modal(
    *,
    is_open: bool = False,
) -> Component:
    return html.Div(
        [
            html.Button(
                id=EDITOR_BACKDROP_ID,
                n_clicks=0,
                className='ada-kpi-definition__modal-backdrop',
                **{'aria-label': 'Cerrar formulario'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.H3('Nueva definición', id=EDITOR_TITLE_ID),
                            html.Button(
                                id=EDITOR_CLOSE_ID,
                                n_clicks=0,
                                className='btn-close',
                                **{'aria-label': 'Cerrar formulario'},
                            ),
                        ],
                        className='modal-header ada-kpi-definition__modal-header',
                    ),
                    html.Div(
                        [
                            _field(
                                'KPI',
                                dbc.Input(
                                    id=EDITOR_KPI_KEY_ID,
                                    type='text',
                                    value='',
                                    disabled=True,
                                    class_name='ada-kpi-definition__input',
                                ),
                            ),
                            html.Div(
                                _field(
                                    'Detalle',
                                    dbc.Textarea(
                                        id=EDITOR_DETAIL_ID,
                                        value='',
                                        placeholder='Describe el significado y contexto del KPI.',
                                        class_name='ada-kpi-definition__textarea',
                                    ),
                                ),
                                id=EDITOR_FORM_ID,
                            ),
                            html.Div(
                                id=EDITOR_VIEW_ID,
                                className='ada-kpi-definition__detail-view',
                                hidden=True,
                            ),
                            html.Div(id=EDITOR_RESULT_ID),
                        ],
                        className='modal-body ada-kpi-definition__modal-body',
                    ),
                    html.Footer(
                        [
                            dbc.Button(
                                'Cancelar',
                                id=EDITOR_CANCEL_ID,
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                            ),
                            dbc.Button(
                                'Guardar definición',
                                id=EDITOR_SAVE_ID,
                                n_clicks=0,
                                color='primary',
                            ),
                        ],
                        className='modal-footer ada-kpi-definition__modal-actions',
                    ),
                ],
                className='modal-content ada-kpi-definition__modal-card',
            ),
        ],
        id=EDITOR_MODAL_ID,
        className=_MODAL_OPEN if is_open else _MODAL_CLOSED,
    )


def build_kpi_definition_detail_view(
    definition: KpiDefinition,
) -> Component:
    fields = _ordered_fields(definition.fields)
    if not fields:
        return html.Div(
            [
                html.Strong('Sin información descriptiva.'),
                html.Span('Esta definición no contiene campos descriptivos.'),
            ],
            className='ada-kpi-definition__detail-empty',
        )

    return html.Div(
        [
            html.Div(
                [
                    html.Span(_field_label(name)),
                    html.P(value if value is not None and value.strip() else '—'),
                ],
                className='ada-kpi-definition__detail-item',
            )
            for name, value in fields
        ],
        className='ada-kpi-definition__detail-list',
    )


def _toolbar(
    query: KpiDefinitionQuery,
    *,
    authority: KpiDefinitionAuthorityCatalog | None,
) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.H2('Definiciones KPI'),
                    html.P(
                        'Administra la información descriptiva de los KPI autorizados por Configuración KPI.'
                    ),
                ],
                className='ada-kpi-definition__heading',
            ),
            html.Div(
                [
                    dbc.Input(
                        id=SEARCH_ID,
                        type='search',
                        value=query.search,
                        debounce=True,
                        placeholder='Buscar KPI…',
                        class_name='ada-kpi-definition__search',
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=STATUS_FILTER_ID,
                            options=_status_options(authority),
                            value=query.status.value,
                            clearable=False,
                            searchable=False,
                            style=configuration_dash_select_style(),
                        ),
                        className=(
                            'ada-configuration-dash-select-shell '
                            'ada-kpi-definition__status-filter'
                        ),
                    ),
                ],
                className='ada-kpi-definition__filters',
            ),
        ],
        className='ada-kpi-definition__toolbar',
    )


def _row(
    item: KpiDefinitionEditorItem,
    *,
    can_manage: bool,
) -> Component:
    return html.Tr(
        [
            html.Td(
                html.Span(
                    item.kpi_key,
                    className='ada-kpi-definition__kpi-key',
                ),
                **{'data-label': 'KPI'},
            ),
            html.Td(
                html.Span(
                    _status_label(item.status),
                    className=(
                        'ada-kpi-definition__status '
                        f'ada-kpi-definition__status--{item.status.value}'
                    ),
                ),
                **{'data-label': 'Estado'},
            ),
            html.Td(
                _actions(item, can_manage=can_manage),
                className='ada-kpi-definition__actions-cell',
                **{'data-label': 'Acciones'},
            ),
        ],
        className='ada-kpi-definition__row',
    )


def _actions(
    item: KpiDefinitionEditorItem,
    *,
    can_manage: bool,
) -> Component:
    actions: list[Component] = []

    if item.status is KpiDefinitionEditorStatus.PENDING:
        actions.append(
            dbc.Button(
                'Agregar',
                id=row_add_id(item.kpi_key),
                n_clicks=0,
                disabled=not can_manage,
                color='secondary',
                outline=True,
                size='sm',
            )
        )
    else:
        actions.append(
            dbc.Button(
                'Ver detalle',
                id=row_view_id(item.kpi_key),
                n_clicks=0,
                color='secondary',
                outline=True,
                size='sm',
            )
        )
        if item.status is KpiDefinitionEditorStatus.DEFINED:
            actions.append(
                dbc.Button(
                    'Editar',
                    id=row_edit_id(item.kpi_key),
                    n_clicks=0,
                    disabled=not can_manage,
                    color='secondary',
                    outline=True,
                    size='sm',
                )
            )
        actions.append(
            dbc.Button(
                'Eliminar',
                id=row_delete_id(item.kpi_key),
                n_clicks=0,
                disabled=not can_manage,
                color='danger',
                outline=True,
                size='sm',
            )
        )

    return html.Div(actions, className='ada-kpi-definition__row-actions')


def _field(label: str, control: Component) -> Component:
    return html.Label(
        [
            html.Span(label, className='ada-kpi-definition__field-label'),
            control,
        ],
        className='ada-kpi-definition__field',
    )


def _empty_row(reason: str) -> Component:
    return html.Tr(
        html.Td('', colSpan=3, **{'aria-hidden': 'true'}),
        className='ada-kpi-definition__row ada-kpi-definition__row--empty',
        **{
            'aria-hidden': 'true',
            'data-row-slot': 'empty',
            'data-empty-reason': reason,
        },
    )


def _placeholder_row(index: int) -> Component:
    return html.Tr(
        [
            html.Td('', **{'aria-hidden': 'true'}),
            html.Td('', **{'aria-hidden': 'true'}),
            html.Td('', **{'aria-hidden': 'true'}),
        ],
        className='ada-kpi-definition__row ada-kpi-definition__row--placeholder',
        **{
            'aria-hidden': 'true',
            'data-row-slot': f'placeholder-{index}',
        },
    )


def _empty_state(
    *,
    icon: str,
    title: str,
    detail: str,
    reason: str,
) -> Component:
    return html.Div(
        [
            html.Span(
                icon,
                className='ada-kpi-definition__empty-icon',
                **{'aria-hidden': 'true'},
            ),
            html.Strong(title),
            html.Span(detail),
        ],
        className='ada-kpi-definition__empty-state',
        role='status',
        **{'data-empty-state': reason},
    )


def _dependency_content(reason: str | None) -> Component | None:
    if reason is None:
        return None
    return html.Div(
        [
            html.Strong('Definiciones KPI no disponibles'),
            html.Span(reason),
        ],
        className='ada-kpi-definition__dependency-copy',
    )


def _status_label(status: KpiDefinitionEditorStatus) -> str:
    return {
        KpiDefinitionEditorStatus.PENDING: 'Pendiente',
        KpiDefinitionEditorStatus.DEFINED: 'Definido',
        KpiDefinitionEditorStatus.ORPHAN: 'Huérfano',
    }[status]


def _status_options(
    authority: KpiDefinitionAuthorityCatalog | None,
) -> list[dict[str, object]]:
    disabled = authority is None
    return [
        {'label': 'Todos', 'value': KpiDefinitionStatusFilter.ALL.value},
        {
            'label': 'Pendientes',
            'value': KpiDefinitionStatusFilter.PENDING.value,
            'disabled': disabled,
        },
        {
            'label': 'Definidos',
            'value': KpiDefinitionStatusFilter.DEFINED.value,
            'disabled': disabled,
        },
        {
            'label': 'Huérfanos',
            'value': KpiDefinitionStatusFilter.ORPHAN.value,
            'disabled': disabled,
        },
    ]


def _ordered_fields(
    fields: Mapping[str, str | None],
) -> tuple[tuple[str, str | None], ...]:
    detail = [('detail', fields['detail'])] if 'detail' in fields else []
    others = sorted(
        (
            (name, value)
            for name, value in fields.items()
            if name != 'detail'
        ),
        key=lambda item: item[0].casefold(),
    )
    return tuple((*detail, *others))


def _field_label(name: str) -> str:
    if name == 'detail':
        return 'Detalle'
    return name.replace('_', ' ').strip().capitalize()
