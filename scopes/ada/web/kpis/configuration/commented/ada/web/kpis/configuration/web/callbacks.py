from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada.web.configuration import (
    ConfigurationPageRequest,
    SortDirection,
    build_configuration_pagination,
)
from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiConfigurationBinding,
    KpiConfigurationValidationError,
)
from ada.web.kpis.configuration.web.ids import (
    ACTIVE_FILTERS_ID,
    ADD_BUTTON_ID,
    AVAILABILITY_ID,
    CONFIGURATION_STORE_ID,
    DATA_MODE_FILTER_ID,
    DESTINATION_FILTER_ID,
    EDITOR_CANCEL_ID,
    EDITOR_DESTINATIONS_ID,
    EDITOR_HOURS_ID,
    EDITOR_KPI_KEY_ID,
    EDITOR_LATEST_ID,
    EDITOR_MODAL_ID,
    EDITOR_RESULT_ID,
    EDITOR_SAVE_ID,
    EDITOR_SERIES_ID,
    EDITOR_STORE_ID,
    EDITOR_TITLE_ID,
    GRID_CONTAINER_ID,
    PAGINATION_CONTAINER_ID,
    PAGINATION_PREFIX,
    QUERY_STORE_ID,
    ROW_DELETE_TYPE,
    ROW_EDIT_TYPE,
    SEARCH_ID,
    row_delete_id,
    row_edit_id,
)
from ada.web.kpis.configuration.web.layout import (
    creation_state,
    load_catalog,
    query_document,
    resolved_catalog,
)
from ada.web.kpis.configuration.web.models import KpiConfigurationEditorContext
from ada.web.kpis.configuration.web.presentation import (
    build_kpi_configuration_active_filters,
    build_kpi_configuration_grid,
)
from ada.web.kpis.configuration.web.query import (
    KpiConfigurationDataMode,
    KpiConfigurationQuery,
    KpiConfigurationSortField,
    query_kpi_configuration,
)


def register_kpi_configuration_editor_callbacks(
    app: object,
    context: KpiConfigurationEditorContext,
) -> None:
    @app.callback(
        Output(QUERY_STORE_ID, 'data'),
        Input(SEARCH_ID, 'value'),
        Input(DESTINATION_FILTER_ID, 'value'),
        Input(DATA_MODE_FILTER_ID, 'value'),
        Input(f'{PAGINATION_PREFIX}--pagination-previous', 'n_clicks'),
        Input(f'{PAGINATION_PREFIX}--pagination-next', 'n_clicks'),
        Input(f'{PAGINATION_PREFIX}--pagination-page-size', 'value'),
        Input({'type': f'{PAGINATION_PREFIX}--pagination-page', 'index': ALL}, 'n_clicks'),
        State(QUERY_STORE_ID, 'data'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def update_query(
        search: str | None,
        destination_keys: list[str] | None,
        data_mode: str | None,
        _previous_clicks: int | None,
        _next_clicks: int | None,
        page_size: int | None,
        _page_clicks: list[int | None] | None,
        query_data: dict[str, object] | None,
        configuration_data: dict[str, object] | None,
    ):
        current = parse_query(query_data)
        trigger = ctx.triggered_id
        size = page_size if page_size in {10, 20} else current.page.page_size
        mode = parse_data_mode(data_mode)
        page_number = current.page.page_number

        if isinstance(trigger, str) and trigger in {
            SEARCH_ID,
            DESTINATION_FILTER_ID,
            DATA_MODE_FILTER_ID,
        }:
            page_number = 1
        elif trigger == f'{PAGINATION_PREFIX}--pagination-page-size':
            page_number = 1
        elif trigger == f'{PAGINATION_PREFIX}--pagination-previous':
            page_number = max(1, page_number - 1)
        elif trigger == f'{PAGINATION_PREFIX}--pagination-next':
            probe = KpiConfigurationQuery(
                search=str(search or ''),
                destination_keys=tuple(destination_keys or ()),
                data_mode=mode,
                sort_field=current.sort_field,
                sort_direction=current.sort_direction,
                page=ConfigurationPageRequest(page_number=1, page_size=size),
            )
            page_count = query_kpi_configuration(
                parse_configuration(configuration_data),
                probe,
            ).page_count
            page_number = min(page_count, page_number + 1)
        elif (
            isinstance(trigger, dict)
            and trigger.get('type') == f'{PAGINATION_PREFIX}--pagination-page'
        ):
            try:
                page_number = max(1, int(trigger.get('index', 1)))
            except (TypeError, ValueError):
                page_number = current.page.page_number

        updated = KpiConfigurationQuery(
            search=str(search or ''),
            destination_keys=tuple(destination_keys or ()),
            data_mode=mode,
            sort_field=current.sort_field,
            sort_direction=current.sort_direction,
            page=ConfigurationPageRequest(
                page_number=page_number,
                page_size=size,
            ),
        )
        return query_document(updated)

    @app.callback(
        Output(ACTIVE_FILTERS_ID, 'children'),
        Output(GRID_CONTAINER_ID, 'children'),
        Output(PAGINATION_CONTAINER_ID, 'children'),
        Output(ADD_BUTTON_ID, 'disabled'),
        Output(AVAILABILITY_ID, 'children'),
        Output(AVAILABILITY_ID, 'hidden'),
        Output(DESTINATION_FILTER_ID, 'options'),
        Output(EDITOR_DESTINATIONS_ID, 'options'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(QUERY_STORE_ID, 'data'),
    )
    def render_editor(
        configuration_data: dict[str, object] | None,
        query_data: dict[str, object] | None,
    ):
        configuration = parse_configuration(configuration_data)
        query = parse_query(query_data)
        loaded = load_catalog(context)
        catalog = resolved_catalog(loaded)
        creation_enabled, reason = creation_state(loaded)
        can_manage = context.can_manage()
        page = query_kpi_configuration(configuration, query)
        options = destination_options(catalog)

        return (
            build_kpi_configuration_active_filters(
                query,
                destination_catalog=catalog,
            ),
            build_kpi_configuration_grid(
                page,
                destination_catalog=catalog,
                query=query,
                can_manage=can_manage,
            ),
            build_configuration_pagination(page, id_prefix=PAGINATION_PREFIX),
            not creation_enabled or not can_manage,
            availability_content(reason),
            reason is None,
            options,
            options,
        )

    @app.callback(
        Output(EDITOR_MODAL_ID, 'is_open'),
        Output(EDITOR_TITLE_ID, 'children'),
        Output(EDITOR_KPI_KEY_ID, 'value'),
        Output(EDITOR_KPI_KEY_ID, 'disabled'),
        Output(EDITOR_LATEST_ID, 'value'),
        Output(EDITOR_SERIES_ID, 'value'),
        Output(EDITOR_HOURS_ID, 'value'),
        Output(EDITOR_DESTINATIONS_ID, 'value'),
        Output(EDITOR_RESULT_ID, 'children'),
        Output(EDITOR_STORE_ID, 'data'),
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Input(ADD_BUTTON_ID, 'n_clicks'),
        Input(row_edit_id(ALL), 'n_clicks'),
        Input(EDITOR_CANCEL_ID, 'n_clicks'),
        Input(EDITOR_SAVE_ID, 'n_clicks'),
        State(EDITOR_STORE_ID, 'data'),
        State(EDITOR_KPI_KEY_ID, 'value'),
        State(EDITOR_LATEST_ID, 'value'),
        State(EDITOR_SERIES_ID, 'value'),
        State(EDITOR_HOURS_ID, 'value'),
        State(EDITOR_DESTINATIONS_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def edit_kpi(
        add_clicks: int | None,
        _edit_clicks: list[int | None] | None,
        _cancel_clicks: int | None,
        save_clicks: int | None,
        editor_data: dict[str, object] | None,
        kpi_key: str | None,
        latest_values: list[str] | None,
        series_values: list[str] | None,
        hours: int | float | None,
        destination_keys: list[str] | None,
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        configuration = parse_configuration(configuration_data)

        if trigger == EDITOR_CANCEL_ID:
            return editor_response(closed=True)

        if trigger == ADD_BUTTON_ID and click_is_real(add_clicks):
            allowed, reason = creation_state(load_catalog(context))
            if not allowed:
                return editor_response(
                    error=reason or 'No es posible crear KPI en este momento.'
                )
            if not context.can_manage():
                return editor_response(error='No tienes permisos para administrar KPI.')
            return editor_response(
                title='Nuevo KPI',
                key='',
                key_disabled=False,
                latest=True,
                series=False,
                hours=None,
                destinations=(),
                editor={'mode': 'create'},
            )

        if isinstance(trigger, dict) and trigger.get('type') == ROW_EDIT_TYPE:
            key = str(trigger.get('key', '')).strip()
            try:
                binding = configuration.binding(key)
            except KpiConfigurationValidationError:
                binding = None
            if binding is None:
                return editor_response(error='El KPI seleccionado ya no existe.')
            return editor_response(
                title='Editar KPI',
                key=binding.kpi_key,
                key_disabled=True,
                latest=binding.latest_enabled,
                series=binding.series_enabled,
                hours=binding.series_hours,
                destinations=binding.destination_keys,
                editor={'mode': 'edit', 'key': binding.kpi_key},
            )

        if trigger != EDITOR_SAVE_ID or not click_is_real(save_clicks):
            return editor_response(no_change=True)

        if not context.can_manage():
            return editor_response_from_state(
                editor_data,
                kpi_key=kpi_key,
                latest_values=latest_values,
                series_values=series_values,
                hours=hours,
                destinations=destination_keys,
                error='No tienes permisos para administrar KPI.',
            )

        try:
            updated = save_binding(
                configuration,
                editor_data,
                kpi_key=kpi_key,
                latest_enabled='enabled' in (latest_values or ()),
                series_enabled='enabled' in (series_values or ()),
                series_hours=hours,
                destination_keys=tuple(destination_keys or ()),
                creation_allowed=creation_state(load_catalog(context))[0],
            )
        except ValueError as error:
            return editor_response_from_state(
                editor_data,
                kpi_key=kpi_key,
                latest_values=latest_values,
                series_values=series_values,
                hours=hours,
                destinations=destination_keys,
                error=str(error),
            )

        return editor_response(
            closed=True,
            configuration=updated.to_document(),
        )

    @app.callback(
        Output(EDITOR_HOURS_ID, 'disabled'),
        Input(EDITOR_SERIES_ID, 'value'),
    )
    def toggle_series_hours(series_values: list[str] | None):
        return 'enabled' not in (series_values or ())

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Input(row_delete_id(ALL), 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def delete_kpi(
        _delete_clicks: list[int | None] | None,
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or trigger.get('type') != ROW_DELETE_TYPE:
            return no_update
        if not context.can_manage():
            return no_update
        key = str(trigger.get('key', '')).strip()
        configuration = parse_configuration(configuration_data)
        try:
            exists = configuration.binding(key)
        except KpiConfigurationValidationError:
            exists = None
        if exists is None:
            return no_update
        return KpiConfiguration(
            bindings=tuple(
                binding
                for binding in configuration.bindings
                if binding.kpi_key != key
            )
        ).to_document()


def parse_configuration(
    document: dict[str, object] | None,
) -> KpiConfiguration:
    if not isinstance(document, dict):
        return KpiConfiguration()
    try:
        return KpiConfiguration.from_document(document)
    except KpiConfigurationValidationError:
        return KpiConfiguration()


def parse_query(
    document: dict[str, object] | None,
) -> KpiConfigurationQuery:
    data = document or {}
    try:
        return KpiConfigurationQuery(
            search=str(data.get('search', '')),
            destination_keys=tuple(data.get('destination_keys', ())),
            data_mode=KpiConfigurationDataMode(str(data.get('data_mode', 'all'))),
            sort_field=KpiConfigurationSortField(str(data.get('sort_field', 'kpi_key'))),
            sort_direction=SortDirection(str(data.get('sort_direction', 'asc'))),
            page=ConfigurationPageRequest(
                page_number=int(data.get('page_number', 1)),
                page_size=int(data.get('page_size', 10)),
            ),
        )
    except (TypeError, ValueError):
        return KpiConfigurationQuery()


def parse_data_mode(
    value: str | None,
) -> KpiConfigurationDataMode:
    try:
        return KpiConfigurationDataMode(str(value or 'all'))
    except ValueError:
        return KpiConfigurationDataMode.ALL


def save_binding(
    configuration: KpiConfiguration,
    editor_data: dict[str, object] | None,
    *,
    kpi_key: str | None,
    latest_enabled: bool,
    series_enabled: bool,
    series_hours: int | float | None,
    destination_keys: tuple[str, ...],
    creation_allowed: bool,
) -> KpiConfiguration:
    mode = str((editor_data or {}).get('mode', ''))
    if mode not in {'create', 'edit'}:
        raise ValueError('No hay un KPI abierto para edición.')

    key = str(kpi_key or '').strip()
    if mode == 'edit':
        key = str((editor_data or {}).get('key', '')).strip()

    if not key:
        raise ValueError('Ingresa un identificador de KPI.')
    if mode == 'create' and not creation_allowed:
        raise ValueError('Configura al menos un componente en Herramienta antes de crear KPI.')
    if mode == 'create':
        try:
            exists = configuration.binding(key)
        except KpiConfigurationValidationError:
            exists = None
        if exists is not None:
            raise ValueError('Ya existe un KPI con ese identificador.')
    if not destination_keys:
        raise ValueError('Selecciona al menos un componente o destino.')

    resolved_hours: int | None = None
    if series_enabled:
        if isinstance(series_hours, bool) or series_hours is None:
            raise ValueError('La serie temporal requiere una ventana entre 1 y 24 horas.')
        numeric = float(series_hours)
        if not numeric.is_integer() or not 1 <= numeric <= 24:
            raise ValueError('La serie temporal requiere una ventana entre 1 y 24 horas.')
        resolved_hours = int(numeric)

    try:
        binding = KpiConfigurationBinding(
            kpi_key=key,
            destination_keys=destination_keys,
            latest_enabled=latest_enabled,
            series_enabled=series_enabled,
            series_hours=resolved_hours,
        )
    except KpiConfigurationValidationError as error:
        raise ValueError('Revisa los datos configurados para este KPI.') from error

    bindings: list[KpiConfigurationBinding] = []
    replaced = False
    for current in configuration.bindings:
        if mode == 'edit' and current.kpi_key == key:
            bindings.append(binding)
            replaced = True
        else:
            bindings.append(current)

    if mode == 'create':
        bindings.append(binding)
    elif not replaced:
        raise ValueError('El KPI seleccionado ya no existe.')

    return KpiConfiguration(bindings=tuple(bindings))


def destination_options(catalog) -> list[dict[str, str]]:
    names = {
        'global_indicators': 'Indicadores globales',
        'time_status': 'Estado temporal',
    }
    return [
        {
            'label': names.get(item.key, item.display_name),
            'value': item.key,
        }
        for item in catalog.destinations
    ]


def availability_content(reason: str | None) -> object:
    if reason is None:
        return None
    return html.Div(
        [
            html.Strong('Creación de KPI no disponible'),
            html.Span(reason),
        ],
        className='ada-kpi-configuration__availability-copy',
    )


def editor_response(
    *,
    closed: bool = False,
    title: str = 'Nuevo KPI',
    key: str | None = '',
    key_disabled: bool = False,
    latest: bool = True,
    series: bool = False,
    hours: int | float | None = None,
    destinations: tuple[str, ...] | list[str] = (),
    error: str | None = None,
    editor: dict[str, object] | None = None,
    configuration: dict[str, object] | object = no_update,
    no_change: bool = False,
):
    if no_change:
        return (no_update,) * 11
    if closed:
        return (
            False,
            'Nuevo KPI',
            '',
            False,
            ['enabled'],
            [],
            None,
            [],
            None,
            None,
            configuration,
        )
    return (
        True,
        title,
        key,
        key_disabled,
        ['enabled'] if latest else [],
        ['enabled'] if series else [],
        hours,
        list(destinations),
        _error(error) if error else None,
        editor,
        configuration,
    )


def editor_response_from_state(
    editor_data: dict[str, object] | None,
    *,
    kpi_key: str | None,
    latest_values: list[str] | None,
    series_values: list[str] | None,
    hours: int | float | None,
    destinations: list[str] | None,
    error: str,
):
    editing = str((editor_data or {}).get('mode', '')) == 'edit'
    return editor_response(
        title='Editar KPI' if editing else 'Nuevo KPI',
        key=kpi_key,
        key_disabled=editing,
        latest='enabled' in (latest_values or ()),
        series='enabled' in (series_values or ()),
        hours=hours,
        destinations=tuple(destinations or ()),
        error=error,
        editor=editor_data,
    )


def click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )
