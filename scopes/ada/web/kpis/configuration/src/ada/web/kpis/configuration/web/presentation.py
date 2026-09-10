from __future__ import annotations

from collections.abc import Mapping

import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.development.base_component import Component

from ada.web.configuration import (
    ConfigurationMutationState,
    ConfigurationMutationStatus,
    ConfigurationPage,
    build_configuration_pagination,
    configuration_dash_select_style,
)
from ada.web.kpis.configuration import (
    KpiConfigurationBinding,
    KpiDestinationCatalog,
)
from ada.web.kpis.configuration.web.ids import (
    ACTIVE_FILTERS_ID,
    ADD_BUTTON_ID,
    AVAILABILITY_ID,
    DATA_MODE_FILTER_ID,
    DESTINATION_FILTER_ID,
    EDITOR_BACKDROP_ID,
    EDITOR_CANCEL_ID,
    EDITOR_CLOSE_ID,
    EDITOR_DESTINATIONS_ID,
    EDITOR_HOURS_ID,
    EDITOR_KPI_KEY_ID,
    EDITOR_LATEST_ID,
    EDITOR_MODAL_ID,
    EDITOR_RESULT_ID,
    EDITOR_SAVE_ID,
    EDITOR_SERIES_ID,
    EDITOR_TITLE_ID,
    GRID_CONTAINER_ID,
    PAGINATION_CONTAINER_ID,
    PAGINATION_PREFIX,
    ROOT_ID,
    SEARCH_ID,
    TABLE_BODY_ID,
    row_delete_id,
    row_edit_id,
)
from ada.web.kpis.configuration.web.query import (
    KpiConfigurationDataMode,
    KpiConfigurationQuery,
)

_SYSTEM_DESTINATION_LABELS = {
    'global_indicators': 'Indicadores globales',
    'time_status': 'Estado temporal',
}

_MODAL_CLOSED = 'ada-kpi-configuration__modal'
_MODAL_OPEN = 'ada-kpi-configuration__modal ada-kpi-configuration__modal--open'


def build_kpi_configuration_editor(
    page: ConfigurationPage[KpiConfigurationBinding],
    *,
    destination_catalog: KpiDestinationCatalog,
    query: KpiConfigurationQuery | None = None,
    mutation: ConfigurationMutationState | None = None,
    creation_enabled: bool = True,
    creation_disabled_reason: str | None = None,
    can_manage: bool = True,
) -> Component:
    if not isinstance(page, ConfigurationPage):
        raise TypeError('KPI configuration editor requires a ConfigurationPage')
    if not isinstance(destination_catalog, KpiDestinationCatalog):
        raise TypeError('KPI configuration editor requires a KpiDestinationCatalog')

    resolved_query = query or KpiConfigurationQuery(page=page.request)
    resolved_mutation = mutation or ConfigurationMutationState()

    return html.Section(
        [
            _toolbar(
                destination_catalog=destination_catalog,
                query=resolved_query,
                mutation=resolved_mutation,
                creation_enabled=creation_enabled,
                can_manage=can_manage,
            ),
            html.Div(
                _availability_content(creation_disabled_reason),
                id=AVAILABILITY_ID,
                className='ada-kpi-configuration__availability',
                hidden=creation_disabled_reason is None,
            ),
            html.Div(
                build_kpi_configuration_active_filters(
                    resolved_query,
                    destination_catalog=destination_catalog,
                ),
                id=ACTIVE_FILTERS_ID,
            ),
            html.Div(
                build_kpi_configuration_grid(
                    page,
                    destination_catalog=destination_catalog,
                    mutation=resolved_mutation,
                    query=resolved_query,
                    can_manage=can_manage,
                ),
                id=GRID_CONTAINER_ID,
            ),
            html.Div(
                build_configuration_pagination(page, id_prefix=PAGINATION_PREFIX),
                id=PAGINATION_CONTAINER_ID,
            ),
            build_kpi_configuration_editor_modal(
                destination_catalog=destination_catalog,
            ),
        ],
        id=ROOT_ID,
        className='ada-kpi-configuration atlanticus-bootstrap',
        **{'data-ada-kpi-configuration': 'true'},
    )


def build_kpi_configuration_active_filters(
    query: KpiConfigurationQuery,
    *,
    destination_catalog: KpiDestinationCatalog,
) -> Component:
    names = _destination_names(destination_catalog)
    chips: list[Component] = []
    if query.search:
        chips.append(_filter_chip(f'Búsqueda: {query.search}'))
    for key in query.destination_keys:
        chips.append(_filter_chip(names.get(key, key)))
    if query.data_mode is not KpiConfigurationDataMode.ALL:
        chips.append(_filter_chip(_data_mode_label(query.data_mode)))
    return html.Div(
        chips,
        className='ada-kpi-configuration__active-filters',
        hidden=not chips,
    )


def build_kpi_configuration_grid(
    page: ConfigurationPage[KpiConfigurationBinding],
    *,
    destination_catalog: KpiDestinationCatalog,
    mutation: ConfigurationMutationState | None = None,
    query: KpiConfigurationQuery | None = None,
    can_manage: bool = True,
) -> Component:
    resolved_query = query or KpiConfigurationQuery(page=page.request)
    resolved_mutation = mutation or ConfigurationMutationState()
    names = _destination_names(destination_catalog)

    rows: list[Component] = [
        _row(
            binding,
            names=names,
            mutation=resolved_mutation,
            can_manage=can_manage,
        )
        for binding in page.items
    ]

    empty_reason: str | None = None
    empty_state: Component | None = None
    if not page.items:
        filtered = bool(
            resolved_query.search
            or resolved_query.destination_keys
            or resolved_query.data_mode is not KpiConfigurationDataMode.ALL
        )
        if filtered:
            empty_reason = 'filtered'
            empty_state = _empty_state(
                icon='⌕',
                title='No se encontraron KPI.',
                detail='Ajusta o limpia los filtros para volver a mostrar configuraciones.',
                reason=empty_reason,
            )
        else:
            empty_reason = 'empty'
            empty_state = _empty_state(
                icon='+',
                title='Todavía no hay KPI configurados.',
                detail='Agrega el primer KPI cuando la Herramienta tenga componentes disponibles.',
                reason=empty_reason,
            )
        rows.append(_empty_row(empty_reason))

    placeholder_count = page.request.page_size - len(rows)
    rows.extend(_placeholder_row(index) for index in range(max(0, placeholder_count)))

    shell_class = 'ada-kpi-configuration__table-shell'
    if empty_state is not None:
        shell_class += ' ada-kpi-configuration__table-shell--empty'

    return html.Div(
        [
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th('KPI'),
                                html.Th('Último'),
                                html.Th('Serie temporal'),
                                html.Th('Horas'),
                                html.Th('Componentes'),
                                html.Th(
                                    'Acciones',
                                    className='ada-kpi-configuration__actions-heading',
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
                className='ada-kpi-configuration__table',
            ),
            empty_state,
        ],
        className=shell_class,
    )

def build_kpi_configuration_editor_modal(
    *,
    destination_catalog: KpiDestinationCatalog,
    binding: KpiConfigurationBinding | None = None,
    is_open: bool = False,
) -> Component:
    editing = binding is not None
    latest = binding.latest_enabled if binding is not None else True
    series = binding.series_enabled if binding is not None else False
    destinations = list(binding.destination_keys) if binding is not None else []

    return html.Div(
        [
            html.Button(
                id=EDITOR_BACKDROP_ID,
                n_clicks=0,
                className='ada-kpi-configuration__modal-backdrop',
                **{'aria-label': 'Cerrar formulario'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.H3(
                                'Editar KPI' if editing else 'Nuevo KPI',
                                id=EDITOR_TITLE_ID,
                            ),
                            html.Button(
                                id=EDITOR_CLOSE_ID,
                                n_clicks=0,
                                className='btn-close',
                                **{'aria-label': 'Cerrar formulario'},
                            ),
                        ],
                        className='modal-header ada-kpi-configuration__modal-header',
                    ),
                    html.Div(
                        [
                            _field(
                                'Identificador KPI',
                                dbc.Input(
                                    id=EDITOR_KPI_KEY_ID,
                                    type='text',
                                    value=binding.kpi_key if binding is not None else '',
                                    disabled=editing,
                                    placeholder='availability',
                                    autoComplete='off',
                                    class_name='ada-kpi-configuration__input',
                                ),
                            ),
                            html.Div(
                                [
                                    _toggle('Último', EDITOR_LATEST_ID, enabled=latest),
                                    _toggle(
                                        'Serie temporal',
                                        EDITOR_SERIES_ID,
                                        enabled=series,
                                    ),
                                ],
                                className='ada-kpi-configuration__toggle-grid',
                            ),
                            _field(
                                'Ventana histórica',
                                html.Div(
                                    [
                                        dbc.Input(
                                            id=EDITOR_HOURS_ID,
                                            type='number',
                                            min=1,
                                            max=24,
                                            step=1,
                                            value=(
                                                binding.series_hours
                                                if binding is not None
                                                else None
                                            ),
                                            disabled=not series,
                                            class_name='ada-kpi-configuration__input',
                                        ),
                                        html.Span('horas'),
                                    ],
                                    className='ada-kpi-configuration__hours',
                                ),
                            ),
                            _field(
                                'Componentes',
                                html.Div(
                                    dcc.Dropdown(
                                        id=EDITOR_DESTINATIONS_ID,
                                        options=_destination_options(destination_catalog),
                                        value=destinations,
                                        multi=True,
                                        clearable=True,
                                        searchable=True,
                                        placeholder='Seleccionar componentes',
                                        style=configuration_dash_select_style(),
                                        labels={
                                            'search': 'Buscar componente',
                                            'clear_search': 'Limpiar búsqueda',
                                            'select_all': 'Seleccionar todo',
                                            'deselect_all': 'Deseleccionar todo',
                                            'selected_count': '{num_selected} seleccionados',
                                        },
                                    ),
                                    className='ada-configuration-dash-select-shell',
                                ),
                            ),
                            html.Div(id=EDITOR_RESULT_ID),
                        ],
                        className='modal-body ada-kpi-configuration__modal-body',
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
                                'Guardar KPI',
                                id=EDITOR_SAVE_ID,
                                n_clicks=0,
                                color='primary',
                            ),
                        ],
                        className='modal-footer ada-kpi-configuration__modal-actions',
                    ),
                ],
                className='modal-content ada-kpi-configuration__modal-card',
            ),
        ],
        id=EDITOR_MODAL_ID,
        className=_MODAL_OPEN if is_open else _MODAL_CLOSED,
    )

def _toolbar(
    *,
    destination_catalog: KpiDestinationCatalog,
    query: KpiConfigurationQuery,
    mutation: ConfigurationMutationState,
    creation_enabled: bool,
    can_manage: bool,
) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2('Configuración de KPI'),
                            html.P(
                                'Define la entrega de cada KPI y los componentes donde se utiliza.'
                            ),
                        ],
                        className='ada-kpi-configuration__heading',
                    ),
                    dbc.Button(
                        '+ KPI',
                        id=ADD_BUTTON_ID,
                        n_clicks=0,
                        disabled=mutation.busy or not creation_enabled or not can_manage,
                        color='secondary',
                        outline=True,
                        size='sm',
                    ),
                ],
                className='ada-kpi-configuration__title-row',
            ),
            html.Div(
                [
                    dbc.Input(
                        id=SEARCH_ID,
                        type='search',
                        value=query.search,
                        debounce=True,
                        placeholder='Buscar KPI…',
                        class_name='ada-kpi-configuration__search',
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=DESTINATION_FILTER_ID,
                            options=_destination_options(destination_catalog),
                            value=list(query.destination_keys),
                            multi=True,
                            clearable=True,
                            searchable=True,
                            placeholder='Componentes',
                            style=configuration_dash_select_style(),
                            labels={
                                'search': 'Buscar componente',
                                'clear_search': 'Limpiar búsqueda',
                                'select_all': 'Seleccionar todo',
                                'deselect_all': 'Deseleccionar todo',
                                'selected_count': '{num_selected} seleccionados',
                            },
                        ),
                        className=(
                            'ada-configuration-dash-select-shell '
                            'ada-kpi-configuration__filter'
                        ),
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=DATA_MODE_FILTER_ID,
                            options=[
                                {
                                    'label': 'Todos los modos',
                                    'value': KpiConfigurationDataMode.ALL.value,
                                },
                                {
                                    'label': 'Sólo último',
                                    'value': KpiConfigurationDataMode.LATEST.value,
                                },
                                {
                                    'label': 'Sólo serie temporal',
                                    'value': KpiConfigurationDataMode.TIMESERIES.value,
                                },
                                {
                                    'label': 'Último + serie temporal',
                                    'value': (
                                        KpiConfigurationDataMode.LATEST_AND_TIMESERIES.value
                                    ),
                                },
                            ],
                            value=query.data_mode.value,
                            clearable=False,
                            searchable=False,
                            style=configuration_dash_select_style(),
                        ),
                        className=(
                            'ada-configuration-dash-select-shell '
                            'ada-kpi-configuration__filter '
                            'ada-kpi-configuration__filter--mode'
                        ),
                    ),
                ],
                className='ada-kpi-configuration__filters',
            ),
        ],
        className='ada-kpi-configuration__toolbar',
    )

def _availability_content(message: str | None) -> Component | None:
    if message is None:
        return None
    return html.Div(
        [
            html.Strong('Creación de KPI no disponible'),
            html.Span(message),
        ],
        className='ada-kpi-configuration__availability-copy',
    )


def _empty_row(reason: str) -> Component:
    return html.Tr(
        html.Td('', colSpan=6, **{'aria-hidden': 'true'}),
        className='ada-kpi-configuration__row ada-kpi-configuration__row--empty',
        **{
            'aria-hidden': 'true',
            'data-row-slot': 'empty',
            'data-empty-reason': reason,
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
                className='ada-kpi-configuration__empty-icon',
                **{'aria-hidden': 'true'},
            ),
            html.Strong(title),
            html.Span(detail),
        ],
        className='ada-kpi-configuration__empty-state',
        role='status',
        **{'data-empty-state': reason},
    )

def _placeholder_row(index: int) -> Component:
    return html.Tr(
        [html.Td('', **{'aria-hidden': 'true'}) for _ in range(6)],
        className='ada-kpi-configuration__row ada-kpi-configuration__row--placeholder',
        **{
            'aria-hidden': 'true',
            'data-row-slot': 'placeholder',
            'data-placeholder-index': str(index),
        },
    )


def _row(
    binding: KpiConfigurationBinding,
    *,
    names: Mapping[str, str],
    mutation: ConfigurationMutationState,
    can_manage: bool,
) -> Component:
    busy = mutation.blocks(binding.kpi_key)
    status = (
        mutation.status.value
        if mutation.item_key == binding.kpi_key
        else ConfigurationMutationStatus.IDLE.value
    )
    disabled = busy or not can_manage
    return html.Tr(
        [
            html.Td(
                html.Span(binding.kpi_key, className='ada-kpi-configuration__kpi-key'),
                **{'data-label': 'KPI'},
            ),
            html.Td(_boolean_badge(binding.latest_enabled), **{'data-label': 'Último'}),
            html.Td(
                _boolean_badge(binding.series_enabled),
                **{'data-label': 'Serie temporal'},
            ),
            html.Td(
                f'{binding.series_hours} h' if binding.series_hours is not None else '—',
                **{'data-label': 'Horas'},
            ),
            html.Td(
                _destination_chips(binding.destination_keys, names=names),
                **{'data-label': 'Componentes'},
            ),
            html.Td(
                html.Div(
                    [
                        dbc.Button(
                            'Editar',
                            id=row_edit_id(binding.kpi_key),
                            n_clicks=0,
                            disabled=disabled,
                            color='secondary',
                            outline=True,
                            size='sm',
                        ),
                        dbc.Button(
                            'Eliminar',
                            id=row_delete_id(binding.kpi_key),
                            n_clicks=0,
                            disabled=disabled,
                            color='danger',
                            outline=True,
                            size='sm',
                            title=f'Eliminar KPI {binding.kpi_key}',
                        ),
                    ],
                    className='ada-kpi-configuration__row-actions',
                ),
                className='ada-kpi-configuration__actions-cell',
                **{'data-label': 'Acciones'},
            ),
        ],
        className=(
            'ada-kpi-configuration__row ada-kpi-configuration__row--busy'
            if busy
            else 'ada-kpi-configuration__row'
        ),
        **{
            'data-kpi-key': binding.kpi_key,
            'data-mutation-state': status,
            'data-row-slot': 'record',
        },
    )


def _destination_chips(
    destination_keys: tuple[str, ...],
    *,
    names: Mapping[str, str],
) -> Component:
    visible = destination_keys[:2]
    remaining = len(destination_keys) - len(visible)
    children: list[Component] = [
        html.Span(
            names.get(key, key),
            className='ada-kpi-configuration__component-chip',
        )
        for key in visible
    ]
    if remaining > 0:
        children.append(
            html.Span(
                f'+{remaining}',
                className=(
                    'ada-kpi-configuration__component-chip '
                    'ada-kpi-configuration__component-chip--more'
                ),
                title=', '.join(names.get(key, key) for key in destination_keys[2:]),
            )
        )
    return html.Div(children, className='ada-kpi-configuration__components')


def _boolean_badge(enabled: bool) -> Component:
    return html.Span(
        'Sí' if enabled else 'No',
        className=(
            'ada-kpi-configuration__badge ada-kpi-configuration__badge--on'
            if enabled
            else 'ada-kpi-configuration__badge'
        ),
    )


def _filter_chip(label: str) -> Component:
    return html.Span(label, className='ada-kpi-configuration__filter-chip')


def _field(label: str, control: Component) -> Component:
    return html.Label(
        [
            html.Span(label, className='ada-kpi-configuration__field-label'),
            control,
        ],
        className='ada-kpi-configuration__field',
    )


def _toggle(label: str, component_id: str, *, enabled: bool) -> Component:
    return html.Label(
        dcc.Checklist(
            id=component_id,
            options=[{'label': label, 'value': 'enabled'}],
            value=['enabled'] if enabled else [],
            className='ada-kpi-configuration__toggle',
        ),
        className='ada-kpi-configuration__toggle-field',
    )


def _destination_names(catalog: KpiDestinationCatalog) -> dict[str, str]:
    return {
        item.key: _SYSTEM_DESTINATION_LABELS.get(item.key, item.display_name)
        for item in catalog.destinations
    }


def _destination_options(catalog: KpiDestinationCatalog) -> list[dict[str, str]]:
    names = _destination_names(catalog)
    return [
        {'label': names[item.key], 'value': item.key}
        for item in catalog.destinations
    ]


def _data_mode_label(mode: KpiConfigurationDataMode) -> str:
    return {
        KpiConfigurationDataMode.ALL: 'Todos los modos',
        KpiConfigurationDataMode.LATEST: 'Sólo último',
        KpiConfigurationDataMode.TIMESERIES: 'Sólo serie temporal',
        KpiConfigurationDataMode.LATEST_AND_TIMESERIES: 'Último + serie temporal',
    }[mode]
