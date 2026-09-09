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
)
from ada.web.kpis.configuration import (
    KpiConfigurationBinding,
    KpiDestinationCatalog,
)
from ada.web.kpis.management.ids import (
    ADD_BUTTON_ID,
    DATA_MODE_FILTER_ID,
    DELETE_CANCEL_ID,
    DELETE_CONFIRM_ID,
    DELETE_MODAL_ID,
    DESTINATION_FILTER_ID,
    EDITOR_CANCEL_ID,
    EDITOR_DESTINATIONS_ID,
    EDITOR_HOURS_ID,
    EDITOR_KPI_KEY_ID,
    EDITOR_LATEST_ID,
    EDITOR_MODAL_ID,
    EDITOR_SAVE_ID,
    EDITOR_SERIES_ID,
    PAGINATION_PREFIX,
    ROOT_ID,
    SEARCH_ID,
    TABLE_BODY_ID,
)
from ada.web.kpis.management.query import (
    KpiConfigurationDataMode,
    KpiConfigurationQuery,
)


def build_kpi_configuration_management(
    page: ConfigurationPage[KpiConfigurationBinding],
    *,
    destination_catalog: KpiDestinationCatalog,
    query: KpiConfigurationQuery | None = None,
    mutation: ConfigurationMutationState | None = None,
) -> Component:
    if not isinstance(page, ConfigurationPage):
        raise TypeError('KPI management requires a ConfigurationPage')
    if not isinstance(destination_catalog, KpiDestinationCatalog):
        raise TypeError('KPI management requires a KpiDestinationCatalog')

    resolved_query = query or KpiConfigurationQuery(page=page.request)
    resolved_mutation = mutation or ConfigurationMutationState()
    names = {item.key: item.display_name for item in destination_catalog.destinations}

    return html.Section(
        [
            _toolbar(
                destination_catalog=destination_catalog,
                query=resolved_query,
                mutation=resolved_mutation,
            ),
            _active_filters(resolved_query, names=names),
            _grid(
                page,
                names=names,
                mutation=resolved_mutation,
                query=resolved_query,
            ),
            build_configuration_pagination(page, id_prefix=PAGINATION_PREFIX),
            build_kpi_configuration_editor_modal(
                destination_catalog=destination_catalog,
            ),
            build_kpi_configuration_delete_modal(),
        ],
        id=ROOT_ID,
        className='ada-kpi-management',
        **{'data-ada-kpi-management': 'true'},
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

    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle('Edit KPI' if editing else 'Add KPI'),
                close_button=False,
            ),
            dbc.ModalBody(
                [
                    _field(
                        'KPI',
                        dcc.Input(
                            id=EDITOR_KPI_KEY_ID,
                            type='text',
                            value=binding.kpi_key if binding is not None else '',
                            disabled=editing,
                            placeholder='availability',
                            className='ada-kpi-management__input',
                        ),
                    ),
                    html.Div(
                        [
                            _toggle(
                                'Latest',
                                EDITOR_LATEST_ID,
                                enabled=latest,
                            ),
                            _toggle(
                                'Timeseries',
                                EDITOR_SERIES_ID,
                                enabled=series,
                            ),
                        ],
                        className='ada-kpi-management__toggle-grid',
                    ),
                    _field(
                        'History window',
                        html.Div(
                            [
                                dcc.Input(
                                    id=EDITOR_HOURS_ID,
                                    type='number',
                                    min=1,
                                    max=24,
                                    step=1,
                                    value=binding.series_hours if binding is not None else None,
                                    disabled=not series,
                                    className='ada-kpi-management__input',
                                ),
                                html.Span('hours'),
                            ],
                            className='ada-kpi-management__hours',
                        ),
                    ),
                    _field(
                        'Components',
                        dcc.Dropdown(
                            id=EDITOR_DESTINATIONS_ID,
                            options=[
                                {'label': item.display_name, 'value': item.key}
                                for item in destination_catalog.destinations
                            ],
                            value=destinations,
                            multi=True,
                            clearable=True,
                            placeholder='Select one or more components',
                            className='ada-kpi-management__select',
                        ),
                    ),
                ],
                className='ada-kpi-management__modal-body',
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        'Cancel',
                        id=EDITOR_CANCEL_ID,
                        color='light',
                        className='ada-kpi-management__secondary-action',
                    ),
                    dbc.Button(
                        'Save KPI',
                        id=EDITOR_SAVE_ID,
                        color='secondary',
                        className='ada-kpi-management__primary-action',
                    ),
                ]
            ),
        ],
        id=EDITOR_MODAL_ID,
        is_open=is_open,
        centered=True,
        scrollable=True,
        size='lg',
        className='ada-kpi-management__modal',
    )


def build_kpi_configuration_delete_modal(
    *,
    kpi_key: str | None = None,
    is_open: bool = False,
) -> Component:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle('Delete KPI'),
                close_button=False,
            ),
            dbc.ModalBody(
                [
                    html.P(
                        (
                            f'Delete {kpi_key}? This change cannot be undone.'
                            if kpi_key
                            else 'Delete this KPI? This change cannot be undone.'
                        )
                    ),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button('Cancel', id=DELETE_CANCEL_ID, color='light'),
                    dbc.Button('Delete', id=DELETE_CONFIRM_ID, color='danger'),
                ]
            ),
        ],
        id=DELETE_MODAL_ID,
        is_open=is_open,
        centered=True,
        className='ada-kpi-management__modal',
    )


def _toolbar(
    *,
    destination_catalog: KpiDestinationCatalog,
    query: KpiConfigurationQuery,
    mutation: ConfigurationMutationState,
) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2('KPI Configuration'),
                            html.P('Manage delivery modes and component assignments.'),
                        ],
                        className='ada-kpi-management__heading',
                    ),
                    html.Button(
                        '+ Add KPI',
                        id=ADD_BUTTON_ID,
                        type='button',
                        disabled=mutation.busy,
                        className='ada-kpi-management__add',
                    ),
                ],
                className='ada-kpi-management__title-row',
            ),
            html.Div(
                [
                    dcc.Input(
                        id=SEARCH_ID,
                        type='search',
                        value=query.search,
                        debounce=True,
                        placeholder='Search KPI…',
                        className='ada-kpi-management__search',
                    ),
                    dcc.Dropdown(
                        id=DESTINATION_FILTER_ID,
                        options=[
                            {'label': item.display_name, 'value': item.key}
                            for item in destination_catalog.destinations
                        ],
                        value=list(query.destination_keys),
                        multi=True,
                        clearable=True,
                        placeholder='Components',
                        className='ada-kpi-management__filter',
                    ),
                    dcc.Dropdown(
                        id=DATA_MODE_FILTER_ID,
                        options=[
                            {'label': 'All data modes', 'value': KpiConfigurationDataMode.ALL.value},
                            {'label': 'Latest', 'value': KpiConfigurationDataMode.LATEST.value},
                            {'label': 'Timeseries', 'value': KpiConfigurationDataMode.TIMESERIES.value},
                            {
                                'label': 'Latest + Timeseries',
                                'value': KpiConfigurationDataMode.LATEST_AND_TIMESERIES.value,
                            },
                        ],
                        value=query.data_mode.value,
                        clearable=False,
                        searchable=False,
                        className='ada-kpi-management__filter ada-kpi-management__filter--mode',
                    ),
                ],
                className='ada-kpi-management__filters',
            ),
        ],
        className='ada-kpi-management__toolbar',
    )


def _active_filters(
    query: KpiConfigurationQuery,
    *,
    names: Mapping[str, str],
) -> Component:
    chips: list[Component] = []
    if query.search:
        chips.append(_filter_chip(f'Search: {query.search}'))
    for key in query.destination_keys:
        chips.append(_filter_chip(names.get(key, key)))
    if query.data_mode is not KpiConfigurationDataMode.ALL:
        chips.append(_filter_chip(query.data_mode.value.replace('_', ' ').title()))
    return html.Div(
        chips,
        className='ada-kpi-management__active-filters',
        hidden=not chips,
    )


def _grid(
    page: ConfigurationPage[KpiConfigurationBinding],
    *,
    names: Mapping[str, str],
    mutation: ConfigurationMutationState,
    query: KpiConfigurationQuery,
) -> Component:
    rows: list[Component] = [
        _row(binding, names=names, mutation=mutation)
        for binding in page.items
    ]

    empty_reason: str | None = None
    if not page.items:
        filtered = bool(
            query.search
            or query.destination_keys
            or query.data_mode is not KpiConfigurationDataMode.ALL
        )
        if filtered:
            rows.append(
                _empty_row(
                    title='No KPIs match these filters.',
                    detail='Adjust or clear the filters to see KPI configurations.',
                    reason='filtered',
                )
            )
            empty_reason = 'filtered'
        else:
            rows.append(
                _empty_row(
                    title='No KPIs configured yet.',
                    detail='Add the first KPI configuration to begin.',
                    reason='empty',
                )
            )
            empty_reason = 'empty'

    placeholder_count = page.request.page_size - len(rows)
    rows.extend(_placeholder_row(index) for index in range(placeholder_count))

    return html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th('KPI'),
                            html.Th('Latest'),
                            html.Th('Timeseries'),
                            html.Th('Hours'),
                            html.Th('Components'),
                            html.Th('Actions', className='ada-kpi-management__actions-heading'),
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
            className='ada-kpi-management__table',
        ),
        className='ada-kpi-management__table-shell',
    )


def _empty_row(
    *,
    title: str,
    detail: str,
    reason: str,
) -> Component:
    return html.Tr(
        html.Td(
            html.Div(
                [
                    html.Strong(title),
                    html.Span(detail),
                ],
                className='ada-kpi-management__empty',
            ),
            colSpan=6,
        ),
        className='ada-kpi-management__row ada-kpi-management__row--empty',
        **{
            'data-row-slot': 'empty',
            'data-empty-reason': reason,
        },
    )


def _placeholder_row(index: int) -> Component:
    return html.Tr(
        [html.Td('', **{'aria-hidden': 'true'}) for _ in range(6)],
        className='ada-kpi-management__row ada-kpi-management__row--placeholder',
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
) -> Component:
    busy = mutation.blocks(binding.kpi_key)
    status = (
        mutation.status.value
        if mutation.item_key == binding.kpi_key
        else ConfigurationMutationStatus.IDLE.value
    )
    return html.Tr(
        [
            html.Td(html.Code(binding.kpi_key), **{'data-label': 'KPI'}),
            html.Td(_boolean_badge(binding.latest_enabled), **{'data-label': 'Latest'}),
            html.Td(_boolean_badge(binding.series_enabled), **{'data-label': 'Timeseries'}),
            html.Td(
                f'{binding.series_hours} h' if binding.series_hours is not None else '—',
                **{'data-label': 'Hours'},
            ),
            html.Td(
                _destination_chips(binding.destination_keys, names=names),
                **{'data-label': 'Components'},
            ),
            html.Td(
                html.Button(
                    '⋮',
                    id={
                        'type': 'ada-kpi-management--row-actions',
                        'index': binding.kpi_key,
                    },
                    type='button',
                    disabled=busy,
                    className='ada-kpi-management__row-action',
                    **{'aria-label': f'Actions for {binding.kpi_key}'},
                ),
                className='ada-kpi-management__actions-cell',
                **{'data-label': 'Actions'},
            ),
        ],
        className=(
            'ada-kpi-management__row ada-kpi-management__row--busy'
            if busy
            else 'ada-kpi-management__row'
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
            className='ada-kpi-management__component-chip',
        )
        for key in visible
    ]
    if remaining > 0:
        children.append(
            html.Span(
                f'+{remaining}',
                className='ada-kpi-management__component-chip ada-kpi-management__component-chip--more',
                title=', '.join(names.get(key, key) for key in destination_keys[2:]),
            )
        )
    return html.Div(children, className='ada-kpi-management__components')


def _boolean_badge(enabled: bool) -> Component:
    return html.Span(
        'On' if enabled else 'Off',
        className=(
            'ada-kpi-management__badge ada-kpi-management__badge--on'
            if enabled
            else 'ada-kpi-management__badge'
        ),
    )


def _filter_chip(label: str) -> Component:
    return html.Span(label, className='ada-kpi-management__filter-chip')


def _field(label: str, control: Component) -> Component:
    return html.Label(
        [
            html.Span(label, className='ada-kpi-management__field-label'),
            control,
        ],
        className='ada-kpi-management__field',
    )


def _toggle(label: str, component_id: str, *, enabled: bool) -> Component:
    return html.Label(
        dcc.Checklist(
            id=component_id,
            options=[{'label': label, 'value': 'enabled'}],
            value=['enabled'] if enabled else [],
            className='ada-kpi-management__toggle',
        ),
        className='ada-kpi-management__toggle-field',
    )
