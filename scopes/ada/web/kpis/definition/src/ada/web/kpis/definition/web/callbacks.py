from __future__ import annotations

from collections.abc import Mapping

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada.web.configuration import (
    ConfigurationPageRequest,
    build_configuration_pagination,
)
from ada.web.kpis.definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionValidationError,
)
from ada.web.kpis.definition.web.ids import (
    CONFIGURATION_STORE_ID,
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
    EDITOR_STORE_ID,
    EDITOR_TITLE_ID,
    EDITOR_VIEW_ID,
    GRID_CONTAINER_ID,
    PAGINATION_CONTAINER_ID,
    PAGINATION_PREFIX,
    QUERY_STORE_ID,
    ROW_ADD_TYPE,
    ROW_DELETE_TYPE,
    ROW_EDIT_TYPE,
    ROW_VIEW_TYPE,
    SEARCH_ID,
    STATUS_FILTER_ID,
    row_add_id,
    row_delete_id,
    row_edit_id,
    row_view_id,
)
from ada.web.kpis.definition.web.layout import (
    load_authority,
    query_document,
)
from ada.web.kpis.definition.web.models import KpiDefinitionEditorContext
from ada.web.kpis.definition.web.presentation import (
    build_kpi_definition_detail_view,
    build_kpi_definition_grid,
)
from ada.web.kpis.definition.web.query import (
    KpiDefinitionQuery,
    KpiDefinitionStatusFilter,
    query_kpi_definitions,
)


def register_kpi_definition_editor_callbacks(
    app: object,
    context: KpiDefinitionEditorContext,
) -> None:
    @app.callback(
        Output(QUERY_STORE_ID, 'data'),
        Input(SEARCH_ID, 'value'),
        Input(STATUS_FILTER_ID, 'value'),
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
        status: str | None,
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
        selected_status = parse_status(status)
        page_number = current.page.page_number

        if isinstance(trigger, str) and trigger in {SEARCH_ID, STATUS_FILTER_ID}:
            page_number = 1
        elif trigger == f'{PAGINATION_PREFIX}--pagination-page-size':
            page_number = 1
        elif trigger == f'{PAGINATION_PREFIX}--pagination-previous':
            page_number = max(1, page_number - 1)
        elif trigger == f'{PAGINATION_PREFIX}--pagination-next':
            probe = KpiDefinitionQuery(
                search=str(search or ''),
                status=selected_status,
                page=ConfigurationPageRequest(page_number=1, page_size=size),
            )
            page_count = query_kpi_definitions(
                parse_configuration(configuration_data),
                load_authority(context),
                probe,
            ).page_count
            page_number = min(page_count, page_number + 1)
        elif (
            isinstance(trigger, Mapping)
            and trigger.get('type') == f'{PAGINATION_PREFIX}--pagination-page'
        ):
            try:
                page_number = max(1, int(trigger.get('index', 1)))
            except (TypeError, ValueError):
                page_number = current.page.page_number

        updated = KpiDefinitionQuery(
            search=str(search or ''),
            status=selected_status,
            page=ConfigurationPageRequest(
                page_number=page_number,
                page_size=size,
            ),
        )
        return query_document(updated)

    @app.callback(
        Output(GRID_CONTAINER_ID, 'children'),
        Output(PAGINATION_CONTAINER_ID, 'children'),
        Output(DEPENDENCY_ID, 'children'),
        Output(DEPENDENCY_ID, 'hidden'),
        Output(STATUS_FILTER_ID, 'disabled'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(QUERY_STORE_ID, 'data'),
    )
    def render_editor(
        configuration_data: dict[str, object] | None,
        query_data: dict[str, object] | None,
    ):
        configuration = parse_configuration(configuration_data)
        query = parse_query(query_data)
        authority = load_authority(context)
        page = query_kpi_definitions(configuration, authority, query)
        reason = (
            'La proyección de Configuración KPI no está disponible.'
            if authority is None
            else None
        )
        return (
            build_kpi_definition_grid(
                page,
                query=query,
                authority=authority,
                can_manage=context.can_manage(),
            ),
            build_configuration_pagination(page, id_prefix=PAGINATION_PREFIX),
            _dependency_content(reason),
            reason is None,
            authority is None,
        )

    @app.callback(
        Output(EDITOR_MODAL_ID, 'className'),
        Output(EDITOR_TITLE_ID, 'children'),
        Output(EDITOR_KPI_KEY_ID, 'value'),
        Output(EDITOR_FORM_ID, 'hidden'),
        Output(EDITOR_DETAIL_ID, 'value'),
        Output(EDITOR_VIEW_ID, 'hidden'),
        Output(EDITOR_VIEW_ID, 'children'),
        Output(EDITOR_SAVE_ID, 'style'),
        Output(EDITOR_CANCEL_ID, 'children'),
        Output(EDITOR_RESULT_ID, 'children'),
        Output(EDITOR_STORE_ID, 'data'),
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Input(row_add_id(ALL), 'n_clicks'),
        Input(row_view_id(ALL), 'n_clicks'),
        Input(row_edit_id(ALL), 'n_clicks'),
        Input(EDITOR_BACKDROP_ID, 'n_clicks'),
        Input(EDITOR_CLOSE_ID, 'n_clicks'),
        Input(EDITOR_CANCEL_ID, 'n_clicks'),
        Input(EDITOR_SAVE_ID, 'n_clicks'),
        State(EDITOR_STORE_ID, 'data'),
        State(EDITOR_DETAIL_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def edit_definition(
        _add_clicks: list[int | None] | None,
        _view_clicks: list[int | None] | None,
        _edit_clicks: list[int | None] | None,
        _backdrop_clicks: int | None,
        _close_clicks: int | None,
        _cancel_clicks: int | None,
        save_clicks: int | None,
        editor_data: dict[str, object] | None,
        detail: str | None,
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        triggered_value = _triggered_value()
        configuration = parse_configuration(configuration_data)
        authority = load_authority(context)

        if _static_trigger_matches(
            trigger,
            EDITOR_BACKDROP_ID,
            EDITOR_CLOSE_ID,
            EDITOR_CANCEL_ID,
        ):
            return editor_response(closed=True)

        add_key = _pattern_action_key(trigger, ROW_ADD_TYPE, triggered_value)
        if add_key is not None:
            if not context.can_manage():
                return editor_response(error='No tienes permisos para administrar definiciones KPI.')
            if authority is None:
                return editor_response(error='La Configuración KPI no está disponible.')
            if add_key not in authority.keys:
                return editor_response(error='El KPI seleccionado ya no está configurado.')
            if configuration.definition(add_key) is not None:
                return editor_response(error='El KPI seleccionado ya tiene una definición.')
            return editor_response(
                title='Nueva definición',
                key=add_key,
                mode='create',
            )

        view_key = _pattern_action_key(trigger, ROW_VIEW_TYPE, triggered_value)
        if view_key is not None:
            definition = configuration.definition(view_key)
            if definition is None:
                return editor_response(error='La definición seleccionada ya no existe.')
            return editor_response(
                title='Detalle de KPI',
                key=definition.kpi_key,
                form_hidden=True,
                view_hidden=False,
                view=build_kpi_definition_detail_view(definition),
                save_style={'display': 'none'},
                cancel_label='Cerrar',
                mode='view',
            )

        edit_key = _pattern_action_key(trigger, ROW_EDIT_TYPE, triggered_value)
        if edit_key is not None:
            if not context.can_manage():
                return editor_response(error='No tienes permisos para administrar definiciones KPI.')
            if authority is None or edit_key not in authority.keys:
                return editor_response(
                    error='La definición no puede editarse porque su KPI ya no está configurado.'
                )
            definition = configuration.definition(edit_key)
            if definition is None:
                return editor_response(error='La definición seleccionada ya no existe.')
            return editor_response(
                title='Editar definición',
                key=definition.kpi_key,
                detail=definition.fields.get('detail') or '',
                mode='edit',
            )

        if (
            not _static_trigger_matches(trigger, EDITOR_SAVE_ID)
            or not click_is_real(save_clicks)
        ):
            return editor_response(no_change=True)

        if not context.can_manage():
            return editor_response_from_state(
                editor_data,
                detail=detail,
                error='No tienes permisos para administrar definiciones KPI.',
            )

        try:
            updated = save_definition_detail(
                configuration,
                authority,
                editor_data,
                detail=detail,
            )
        except ValueError as error:
            return editor_response_from_state(
                editor_data,
                detail=detail,
                error=str(error),
            )

        return editor_response(
            closed=True,
            configuration=updated.to_document(),
        )

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Input(row_delete_id(ALL), 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def remove_definition(
        _delete_clicks: list[int | None] | None,
        configuration_data: dict[str, object] | None,
    ):
        key = _pattern_action_key(
            ctx.triggered_id,
            ROW_DELETE_TYPE,
            _triggered_value(),
        )
        if key is None or not context.can_manage():
            return no_update
        authority = load_authority(context)
        if authority is None:
            return no_update
        configuration = parse_configuration(configuration_data)
        updated = delete_definition(configuration, key)
        if updated == configuration:
            return no_update
        return updated.to_document()


def parse_configuration(
    document: dict[str, object] | None,
) -> KpiDefinitionConfiguration:
    if not isinstance(document, dict):
        return KpiDefinitionConfiguration()
    try:
        return KpiDefinitionConfiguration.from_document(document)
    except KpiDefinitionValidationError:
        return KpiDefinitionConfiguration()


def parse_query(
    document: dict[str, object] | None,
) -> KpiDefinitionQuery:
    data = document or {}
    try:
        return KpiDefinitionQuery(
            search=str(data.get('search', '')),
            status=KpiDefinitionStatusFilter(str(data.get('status', 'all'))),
            page=ConfigurationPageRequest(
                page_number=int(data.get('page_number', 1)),
                page_size=int(data.get('page_size', 10)),
            ),
        )
    except (TypeError, ValueError):
        return KpiDefinitionQuery()


def parse_status(value: str | None) -> KpiDefinitionStatusFilter:
    try:
        return KpiDefinitionStatusFilter(str(value or 'all'))
    except ValueError:
        return KpiDefinitionStatusFilter.ALL


def save_definition_detail(
    configuration: KpiDefinitionConfiguration,
    authority: KpiDefinitionAuthorityCatalog | None,
    editor_data: dict[str, object] | None,
    *,
    detail: str | None,
) -> KpiDefinitionConfiguration:
    mode = str((editor_data or {}).get('mode', ''))
    key = str((editor_data or {}).get('key', '')).strip()

    if mode not in {'create', 'edit'} or not key:
        raise ValueError('No hay una definición abierta para edición.')
    if authority is None:
        raise ValueError('La Configuración KPI no está disponible.')
    if key not in authority.keys:
        raise ValueError('El KPI seleccionado ya no está configurado.')

    normalized_detail = detail.strip() if isinstance(detail, str) else ''
    if not normalized_detail:
        raise ValueError('Ingresa el detalle de la definición.')

    current = configuration.definition(key)
    if mode == 'create' and current is not None:
        raise ValueError('El KPI seleccionado ya tiene una definición.')
    if mode == 'edit' and current is None:
        raise ValueError('La definición seleccionada ya no existe.')

    fields = dict(current.fields) if current is not None else {}
    fields['detail'] = normalized_detail

    try:
        replacement = KpiDefinition(kpi_key=key, fields=fields)
    except KpiDefinitionValidationError as error:
        raise ValueError('Revisa la información de la definición KPI.') from error

    definitions = []
    replaced = False
    for definition in configuration.definitions:
        if definition.kpi_key == key:
            definitions.append(replacement)
            replaced = True
        else:
            definitions.append(definition)

    if mode == 'create':
        definitions.append(replacement)
    elif not replaced:
        raise ValueError('La definición seleccionada ya no existe.')

    return KpiDefinitionConfiguration(definitions=tuple(definitions))


def delete_definition(
    configuration: KpiDefinitionConfiguration,
    kpi_key: str,
) -> KpiDefinitionConfiguration:
    key = kpi_key.strip() if isinstance(kpi_key, str) else ''
    if not key or configuration.definition(key) is None:
        return configuration
    return KpiDefinitionConfiguration(
        definitions=tuple(
            definition
            for definition in configuration.definitions
            if definition.kpi_key != key
        )
    )


def editor_response(
    *,
    closed: bool = False,
    title: str = 'Nueva definición',
    key: str = '',
    form_hidden: bool = False,
    detail: str = '',
    view_hidden: bool = True,
    view: object = None,
    save_style: dict[str, str] | None = None,
    cancel_label: str = 'Cancelar',
    error: str | None = None,
    mode: str | None = None,
    configuration: dict[str, object] | object = no_update,
    no_change: bool = False,
):
    if no_change:
        return (no_update,) * 12
    if closed:
        return (
            'ada-kpi-definition__modal',
            'Nueva definición',
            '',
            False,
            '',
            True,
            None,
            {},
            'Cancelar',
            None,
            None,
            configuration,
        )
    return (
        'ada-kpi-definition__modal ada-kpi-definition__modal--open',
        title,
        key,
        form_hidden,
        detail,
        view_hidden,
        view,
        save_style or {},
        cancel_label,
        _error(error) if error else None,
        {'mode': mode, 'key': key} if mode else None,
        configuration,
    )


def editor_response_from_state(
    editor_data: dict[str, object] | None,
    *,
    detail: str | None,
    error: str,
):
    mode = str((editor_data or {}).get('mode', ''))
    key = str((editor_data or {}).get('key', '')).strip()
    return editor_response(
        title='Editar definición' if mode == 'edit' else 'Nueva definición',
        key=key,
        detail=detail or '',
        error=error,
        mode=mode,
    )


def click_is_real(clicks: object) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0


def _static_trigger_matches(trigger: object, *component_ids: str) -> bool:
    return isinstance(trigger, str) and trigger in component_ids


def _pattern_action_key(
    trigger: object,
    expected_type: str,
    triggered_value: object,
) -> str | None:
    if not isinstance(trigger, Mapping):
        return None
    if trigger.get('type') != expected_type or not click_is_real(triggered_value):
        return None
    key = str(trigger.get('key', '')).strip()
    return key or None


def _triggered_value() -> object:
    if not ctx.triggered:
        return None
    return ctx.triggered[0].get('value')


def _dependency_content(reason: str | None) -> object:
    if reason is None:
        return None
    return html.Div(
        [
            html.Strong('Definiciones KPI no disponibles'),
            html.Span(reason),
        ],
        className='ada-kpi-definition__dependency-copy',
    )


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )
