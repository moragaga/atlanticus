from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from dash import dcc, html

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.coordinator import ManagerProjectionCoordinator
from atlanticus.web.manager.errors import ManagerError
from atlanticus.web.manager.models import (
    ManagerEntry,
    ManagerModule,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.projection import ProjectionState, resolve_projection_state
from atlanticus.web.manager.registry import ManagerModuleRegistry, ManagerRegisteredItem
from atlanticus.web.manager.web.home import build_manager_home
from atlanticus.web.manager.web.ids import (
    CONTENT_ID,
    HOME_ID,
    LOCATION_ID,
    REFRESH_SIGNAL_ID,
    SIDEBAR_BACKDROP_ID,
    SIDEBAR_CLOSE_ID,
    SIDEBAR_ID,
    SIDEBAR_MODULES_ID,
    SIDEBAR_TOGGLE_ID,
    STATUS_STORE_ID,
    SUMMARY_ID,
    history_preview_open_id,
    module_section_button_id,
    module_section_panel_id,
    module_section_store_id,
    module_status_id,
    workflow_action_id,
    workflow_conflict_details_id,
    workflow_conflict_id,
    workflow_draft_id,
    workflow_draft_status_id,
    workflow_editor_revision_id,
    workflow_history_id,
    workflow_history_preview_body_id,
    workflow_history_preview_close_id,
    workflow_history_preview_heading_id,
    workflow_history_preview_id,
    workflow_history_preview_load_id,
    workflow_history_preview_meta_id,
    workflow_history_preview_store_id,
    workflow_projection_signal_id,
    workflow_refresh_signal_id,
    workflow_result_id,
    workflow_saved_draft_id,
    workflow_saved_draft_status_id,
    workflow_source_verification_id,
    workflow_status_id,
    workflow_validation_id,
    workflow_workspace_command_id,
    workflow_workspace_confirmation_id,
    workflow_workspace_confirmation_message_id,
    workflow_workspace_confirmation_title_id,
    workflow_workspace_reset_signal_id,
)
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import HistoryPage

_STATE_LABELS = {
    ProjectionState.NO_SOURCE: 'Sin fuente',
    ProjectionState.SYNCHRONIZED: 'Actualizada',
    ProjectionState.READY: 'Lista',
    ProjectionState.UNAVAILABLE: 'No disponible',
}


def build_manager_surface(
    *,
    definition: ManagerSurfaceDefinition,
    registry: ManagerModuleRegistry,
    services: ServiceRegistry,
    principal: ManagerPrincipal,
    authorization: ManagerAuthorizationPolicy,
) -> object:
    visible_modules = registry.visible_modules(principal, authorization)
    visible_items = registry.visible_items(principal, authorization)
    return html.Div(
        [
            dcc.Location(id=LOCATION_ID, refresh=False),
            dcc.Store(id=STATUS_STORE_ID, storage_type='memory'),
            dcc.Store(id=REFRESH_SIGNAL_ID, data=0, storage_type='memory'),
            *[
                dcc.Store(id=module.source_signal_id, storage_type='memory')
                for module in visible_modules
                if module.source_signal_id is not None
            ],
            *[_module_stores(module) for module in visible_modules],
            html.Section(id=SUMMARY_ID, className='atlanticus-manager__summary', hidden=True),
            html.Div(
                id=HOME_ID,
                children=build_manager_home(registry=registry, modules=visible_items, states={}),
                className='atlanticus-manager__home-surface',
                hidden=True,
            ),
            html.Button(
                '⚙',
                id=SIDEBAR_TOGGLE_ID,
                className='atlanticus-manager__sidebar-trigger',
                **{'aria-label': 'Abrir administración'},
            ),
            html.Main(id=CONTENT_ID, className='atlanticus-manager__content', hidden=True),
            html.Aside(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.Strong('Administración'),
                                    html.Span('Selecciona lo que quieres administrar.'),
                                ]
                            ),
                            html.Button(
                                '×',
                                id=SIDEBAR_CLOSE_ID,
                                className='atlanticus-ui-icon-button',
                            ),
                        ],
                        className='atlanticus-manager__sidebar-header',
                    ),
                    html.Div(
                        id=SIDEBAR_MODULES_ID,
                        children=build_sidebar_modules(
                            registry=registry,
                            modules=visible_items,
                            current_path=registry.root_route,
                            states={},
                        ),
                        className='atlanticus-manager__sidebar-modules',
                    ),
                ],
                id=SIDEBAR_ID,
                className='atlanticus-manager__sidebar',
            ),
            html.Button(
                id=SIDEBAR_BACKDROP_ID,
                className='atlanticus-manager__sidebar-backdrop',
                **{'aria-label': 'Cerrar administración'},
            ),
        ],
        className='atlanticus-manager atlanticus-manager--surface',
    )


def _module_stores(module: ManagerModule) -> object:
    return html.Div(
        [
            dcc.Store(id=workflow_refresh_signal_id(module.key), data=0, storage_type='memory'),
            dcc.Store(id=workflow_projection_signal_id(module.key), storage_type='memory'),
            dcc.Store(id=workflow_draft_id(module.key), storage_type='memory'),
            dcc.Store(id=workflow_saved_draft_id(module.key), storage_type='local'),
            dcc.Store(id=workflow_validation_id(module.key), storage_type='memory'),
            dcc.Store(id=workflow_source_verification_id(module.key), storage_type='memory'),
            dcc.Store(id=workflow_editor_revision_id(module.key), storage_type='memory'),
            dcc.Store(
                id=workflow_workspace_reset_signal_id(module.key),
                data=0,
                storage_type='memory',
            ),
            dcc.Store(id=workflow_workspace_command_id(module.key), storage_type='memory'),
        ],
        style={'display': 'contents'},
    )


def build_summary(states: Mapping[str, ProjectionState]) -> object:
    values = tuple(states.values())
    total = len(values)
    synchronized = sum(value is ProjectionState.SYNCHRONIZED for value in values)
    ready = sum(value is ProjectionState.READY for value in values)
    errors = sum(value is ProjectionState.UNAVAILABLE for value in values)
    pending = total - synchronized - ready - errors
    return html.Div(
        [
            _summary_item('Total', str(total), 'Configuraciones disponibles'),
            _summary_item('Actualizadas', str(synchronized), 'Source y Projection sincronizadas'),
            _summary_item('Pendientes', str(pending), 'Configuración sin Source publicada'),
            _summary_item('Listas', str(ready), 'Source publicada pendiente de Projection'),
            _summary_item('Con errores', str(errors), 'Estado no disponible'),
        ],
        className='atlanticus-manager__summary-items',
    )


def build_sidebar_modules(
    *,
    registry: ManagerModuleRegistry,
    modules: tuple[ManagerRegisteredItem, ...],
    current_path: str,
    states: Mapping[str, ProjectionState],
) -> tuple[object, ...]:
    result: list[object] = []
    home_class = 'atlanticus-manager__sidebar-link atlanticus-manager__sidebar-link--home'
    if current_path == registry.root_route:
        home_class += ' atlanticus-manager__sidebar-link--active'
    result.append(
        dcc.Link(html.Strong('Manager Home'), href=registry.root_route, className=home_class)
    )
    for group in registry.groups:
        group_items = tuple(item for item in modules if item.group_key == group.key)
        if not group_items:
            continue
        result.append(html.Div(group.title, className='atlanticus-manager__sidebar-group'))
        for item in group_items:
            class_name = 'atlanticus-manager__sidebar-link'
            item_route = registry.route_for(item)
            if item_route == current_path:
                class_name += ' atlanticus-manager__sidebar-link--active'
            status = None
            if isinstance(item, ManagerModule):
                state = states.get(item.key, ProjectionState.UNAVAILABLE)
                status = html.Span(
                    _STATE_LABELS[state],
                    className=f'atlanticus-manager__state atlanticus-manager__state--{state.value}',
                )
            result.append(
                dcc.Link(
                    [
                        html.Div([html.Strong(item.title), html.Span(item.description)]),
                        status,
                    ],
                    href=item_route,
                    className=class_name,
                )
            )
    return tuple(result)


def build_entry_content(*, entry: ManagerEntry, services: ServiceRegistry) -> object:
    return html.Section(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P('Administración', className='atlanticus-manager__eyebrow'),
                            html.H2(entry.title),
                            html.P(entry.description),
                        ],
                        className='atlanticus-manager__module-heading',
                    )
                ],
                className='atlanticus-manager__module-header',
            ),
            entry.layout(services),
        ],
        className='atlanticus-manager__module',
    )


def build_module_content(
    *,
    module: ManagerModule,
    services: ServiceRegistry,
    coordinator: ManagerProjectionCoordinator,
    principal: ManagerPrincipal,
) -> object:
    try:
        status = coordinator.get_status(module.key, principal)
        history = (
            coordinator.list_history(module.key, principal, limit=20)
            if coordinator.can_load_history(module.key, principal)
            else None
        )
        error = None
    except Exception:
        status = None
        history = None
        error = 'No fue posible consultar el estado de configuración.'
    content = module.layout(services)
    preamble = module.preamble(services) if module.preamble is not None else None
    default_section = module.default_section
    return html.Section(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P('Configuración', className='atlanticus-manager__eyebrow'),
                            html.H2(module.title),
                            html.P(module.description),
                        ],
                        className='atlanticus-manager__module-heading',
                    ),
                    _build_module_status(module.key, status),
                ],
                className='atlanticus-manager__module-header',
            ),
            preamble,
            dcc.Store(
                id=module_section_store_id(module.key),
                data=default_section,
                storage_type='memory',
            ),
            html.Nav(
                [
                    html.Button(
                        module.content_section_title,
                        id=module_section_button_id(module.key, 'content'),
                        n_clicks=0,
                        className=_section_button_class(default_section == 'content'),
                    ),
                    html.Button(
                        module.workflow_section_title,
                        id=module_section_button_id(module.key, 'workflow'),
                        n_clicks=0,
                        className=_section_button_class(default_section == 'workflow'),
                    ),
                ],
                className='atlanticus-manager__module-tabs',
            ),
            html.Div(
                content,
                id=module_section_panel_id(module.key, 'content'),
                className=_section_panel_class(default_section == 'content'),
            ),
            html.Div(
                build_workflow_panel(module=module, status=status, history=history, error=error),
                id=module_section_panel_id(module.key, 'workflow'),
                className=_section_panel_class(default_section == 'workflow'),
            ),
        ],
        className='atlanticus-manager__module',
    )


def build_workflow_panel(
    *,
    module: ManagerModule,
    status: ProjectionStatus | None,
    history: HistoryPage | None,
    error: str | None,
) -> object:
    return html.Div(
        [
            html.Div(
                id=workflow_draft_status_id(module.key),
                className='atlanticus-manager__workflow-status atlanticus-manager__workflow-status--draft',
            ),
            html.Div(
                build_workflow_status_content(module=module, status=status, error=error),
                id=workflow_status_id(module.key),
                className='atlanticus-manager__workflow-status atlanticus-manager__workflow-status--published',
            ),
            _build_workflow_actions(module, status),
            html.Div(id=workflow_result_id(module.key), className='atlanticus-manager__workflow-result'),
            html.Div(
                build_workflow_history_content(
                    module=module,
                    status=status,
                    history=history,
                    error=error,
                ),
                id=workflow_history_id(module.key),
                className='atlanticus-manager__workflow-history-slot',
            ),
            _build_history_preview_shell(module),
        ],
        className='atlanticus-manager__workflow',
    )


def build_workflow_status_content(
    *,
    module: ManagerModule,
    status: ProjectionStatus | None,
    error: str | None,
) -> object:
    if error is not None:
        return html.Section(
            [
                _workflow_group_header(
                    'Estado publicado',
                    'Fuente de verdad y Projection activa de esta configuración.',
                ),
                html.Div(
                    'No fue posible consultar el estado publicado en este momento.',
                    className='atlanticus-manager__message atlanticus-manager__message--notice',
                ),
            ],
            className=(
                'atlanticus-manager__workflow-group '
                'atlanticus-manager__workflow-group--published-empty'
            ),
        )
    if status is None or status.source_current_release is None:
        return html.Section(
            [
                _workflow_group_header(
                    'Estado publicado',
                    'Fuente de verdad y Projection activa de esta configuración.',
                ),
                html.Div(
                    'Aún no existe una configuración publicada.',
                    className='atlanticus-manager__workflow-empty',
                ),
            ],
            className=(
                'atlanticus-manager__workflow-group '
                'atlanticus-manager__workflow-group--published-empty'
            ),
        )
    state = resolve_projection_state(status)
    source = status.source_current_release
    projected = status.projected_source_release
    return html.Section(
        [
            _workflow_group_header(
                'Estado publicado',
                'Identidad de Source y release actualmente proyectada.',
                state=state,
            ),
            html.Div(
                [
                    _stage(
                        '4',
                        'Fuente de verdad',
                        module.source_name,
                        (
                            ('Release actual', _short(source.release_id.value)),
                            ('Publicada', _format_datetime(source.published_at_utc)),
                        ),
                    ),
                    _stage(
                        '5',
                        'Proyección activa',
                        module.projection_name,
                        (
                            (
                                'Release proyectada',
                                _short(projected.release_id.value if projected else None),
                            ),
                            (
                                'Publicación de Source',
                                _format_datetime(projected.published_at_utc)
                                if projected
                                else 'Sin registro',
                            ),
                        ),
                    ),
                ],
                className='atlanticus-manager__workflow-stage-grid',
            ),
        ],
        className='atlanticus-manager__workflow-group',
    )


def build_workflow_history_content(
    *,
    module: ManagerModule,
    status: ProjectionStatus | None,
    history: HistoryPage | None,
    error: str | None,
) -> object:
    if error is not None or status is None or history is None:
        return None
    rows = []
    for index, entry in enumerate(history.items):
        release = entry.release_ref
        current = release == status.source_current_release
        active = release == status.projected_source_release
        state = (
            ' · '.join(
                label
                for label, enabled in (
                    ('Fuente actual', current),
                    ('Proyección activa', active),
                )
                if enabled
            )
            or 'Histórica'
        )
        action = None
        if module.history_preview_renderer is not None:
            action = html.Button(
                'Ver release',
                id=history_preview_open_id(
                    module.key,
                    release.release_id.value,
                    release.published_at_utc.isoformat(),
                    f'{index}-{release.published_at_utc.isoformat()}',
                    current=current,
                    active=active,
                ),
                n_clicks=0,
                className='atlanticus-ui-button atlanticus-ui-button--secondary atlanticus-manager__history-preview-open',
            )
        rows.append(
            html.Div(
                [
                    _history_cell('Release', html.Code(_short(release.release_id.value))),
                    _history_cell('Fecha', html.Time(_format_datetime(release.published_at_utc))),
                    _history_cell('Estado', html.Span(state)),
                    _history_cell('Acción', action, action=True),
                ],
                className='atlanticus-manager__history-row',
            )
        )
    header = html.Div(
        [
            html.Span('Release'),
            html.Span('Fecha'),
            html.Span('Estado'),
            html.Span('Acción'),
        ],
        className='atlanticus-manager__history-row atlanticus-manager__history-row--header',
    )
    return html.Section(
        [
            html.H3('Historial publicado'),
            html.P('Cada entrada es una publicación Source inmutable.'),
            header if rows else None,
            html.Div(rows) if rows else _history_empty_state(module.source_name),
        ],
        className='atlanticus-manager__history',
    )


def _build_workflow_actions(module: ManagerModule, status: ProjectionStatus | None) -> object:
    actions = [
        ('1', 'Guardar borrador', 'Guarda el trabajo en este navegador.', 'save-draft'),
        ('2', 'Validar', 'Valida sin modificar Source.', 'validate'),
        (
            '3',
            'Verificar fuente',
            f'Comprueba que {module.source_name} siga en la base esperada.',
            'verify-source',
        ),
        ('4', 'Publicar', f'Publica en {module.source_name}.', 'publish'),
        ('5', 'Proyectar', f'Actualiza {module.projection_name}.', 'project'),
    ]
    return html.Div(
        [
            html.Section(
                [
                    _workflow_group_header(
                        'Workspace local',
                        'Controla el trabajo local sin modificar Source ni Projection.',
                    ),
                    html.Div(
                        [
                            html.Button(
                                'Descartar cambios locales',
                                id=workflow_action_id(module.key, 'discard-local'),
                                n_clicks=0,
                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                disabled=True,
                            ),
                            html.Button(
                                'Recargar',
                                id=workflow_action_id(module.key, 'reload'),
                                n_clicks=0,
                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                            ),
                        ],
                        className='atlanticus-manager__workspace-actions',
                    ),
                    html.Div(
                        id=workflow_saved_draft_status_id(module.key),
                        className='atlanticus-manager__saved-draft-slot',
                    ),
                    html.Div(
                        [
                            html.Button(
                                'Recuperar borrador',
                                id=workflow_action_id(module.key, 'recover-saved-draft'),
                                n_clicks=0,
                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                disabled=True,
                            ),
                            html.Button(
                                'Descartar borrador guardado',
                                id=workflow_action_id(module.key, 'discard-saved-draft'),
                                n_clicks=0,
                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                disabled=True,
                            ),
                        ],
                        className='atlanticus-manager__workspace-actions',
                    ),
                ],
                className='atlanticus-manager__workflow-group',
            ),
            html.Section(
                [
                    _workflow_group_header(
                        'Flujo de publicación',
                        'Avanza en orden: guardar, validar, verificar Source y publicar.',
                    ),
                    html.Section(
                        [
                            html.Div(id=workflow_conflict_details_id(module.key)),
                            html.Div(
                                [
                                    html.Button(
                                        f'Usar versión de {module.source_name}',
                                        id=workflow_action_id(module.key, 'update-source'),
                                        n_clicks=0,
                                        className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                    ),
                                    html.Button(
                                        'Mantener mi borrador',
                                        id=workflow_action_id(module.key, 'keep-draft'),
                                        n_clicks=0,
                                        className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                    ),
                                ],
                                className='atlanticus-manager__conflict-actions',
                            ),
                        ],
                        id=workflow_conflict_id(module.key),
                        className='atlanticus-manager__conflict',
                        hidden=True,
                    ),
                    html.Div(
                        [
                            _action_step(
                                step,
                                title,
                                description,
                                html.Button(
                                    title if action != 'verify-source' else 'Verificar',
                                    id=workflow_action_id(module.key, action),
                                    n_clicks=0,
                                    className='atlanticus-ui-button',
                                    disabled=(
                                        action != 'project' or not _can_project(status)
                                    ),
                                ),
                            )
                            for step, title, description, action in actions
                        ],
                        className='atlanticus-manager__workflow-action-grid',
                    ),
                ],
                className='atlanticus-manager__workflow-group',
            ),
            _workspace_confirmation(module),
        ],
        className='atlanticus-manager__workflow-actions',
    )


def _can_project(status: ProjectionStatus | None) -> bool:
    return bool(
        status is not None
        and status.source_current_release is not None
        and status.alignment is not ProjectionAlignment.CURRENT
    )


def _build_module_status(module_key: str, status: ProjectionStatus | None) -> object:
    state = resolve_projection_state(status) if status is not None else ProjectionState.UNAVAILABLE
    return html.Span(
        _STATE_LABELS[state],
        id=module_status_id(module_key),
        className=f'atlanticus-manager__state atlanticus-manager__state--{state.value}',
    )


def _summary_item(label: str, value: str, detail: str) -> object:
    return html.Article(
        [html.Span(label), html.Strong(value), html.Small(detail)],
        className='atlanticus-manager__summary-item',
    )


def _workflow_group_header(
    title: str,
    description: str,
    *,
    state: ProjectionState | None = None,
) -> object:
    return html.Header(
        [
            html.Div([html.H3(title), html.P(description)]),
            html.Span(
                _STATE_LABELS[state],
                className=f'atlanticus-manager__state atlanticus-manager__state--{state.value}',
            )
            if state is not None
            else None,
        ],
        className='atlanticus-manager__workflow-group-header',
    )


def _stage(step: str, title: str, subtitle: str, items: tuple[tuple[str, str], ...]) -> object:
    return html.Article(
        [
            html.Header(
                [
                    html.Span(step, className='atlanticus-manager__workflow-step-number'),
                    html.Div([html.H4(title), html.P(subtitle)]),
                ],
                className='atlanticus-manager__workflow-stage-header',
            ),
            html.Div(
                [
                    html.Div(
                        [html.Span(label), html.Strong(value)],
                        className='atlanticus-manager__workflow-stage-item',
                    )
                    for label, value in items
                ],
                className='atlanticus-manager__workflow-stage-items',
            ),
        ],
        className='atlanticus-manager__workflow-stage-card',
    )


def _history_empty_state(source_name: str) -> object:
    return html.Div(
        [
            html.Span(
                '↺',
                className='atlanticus-manager__history-empty-icon',
                **{'aria-hidden': 'true'},
            ),
            html.Strong('Aún no hay publicaciones.'),
            html.Span(
                f'Las publicaciones aparecerán aquí después de la primera publicación en '
                f'{source_name}.'
            ),
        ],
        className='atlanticus-manager__history-empty',
        role='status',
    )


def _history_cell(
    label: str,
    value: object | None,
    *,
    action: bool = False,
) -> object:
    return html.Div(
        [
            html.Small(label, className='atlanticus-manager__history-cell-label'),
            value if value is not None else html.Span('—'),
        ],
        className=(
            'atlanticus-manager__history-cell atlanticus-manager__history-cell--action'
            if action
            else 'atlanticus-manager__history-cell'
        ),
    )


def _action_step(step: str, title: str, description: str, action: object) -> object:
    return html.Article(
        [
            html.Div(
                [
                    html.Span(step, className='atlanticus-manager__workflow-step-number'),
                    html.Div([html.Strong(title), html.P(description)]),
                ],
                className='atlanticus-manager__workflow-step-heading',
            ),
            action,
        ],
        className='atlanticus-manager__workflow-action-step',
    )


def _workspace_confirmation(module: ManagerModule) -> object:
    return html.Div(
        html.Div(
            [
                html.H3(id=workflow_workspace_confirmation_title_id(module.key)),
                html.P(id=workflow_workspace_confirmation_message_id(module.key)),
                html.Div(
                    [
                        html.Button(
                            'Cancelar',
                            id=workflow_action_id(module.key, 'workspace-cancel'),
                            n_clicks=0,
                        ),
                        html.Button(
                            'Confirmar',
                            id=workflow_action_id(module.key, 'workspace-confirm'),
                            n_clicks=0,
                        ),
                    ]
                ),
            ]
        ),
        id=workflow_workspace_confirmation_id(module.key),
        hidden=True,
    )


def _build_history_preview_shell(module: ManagerModule) -> object:
    return html.Div(
        [
            dcc.Store(id=workflow_history_preview_store_id(module.key), storage_type='memory'),
            html.Div(
                html.Section(
                    [
                        html.H3(id=workflow_history_preview_heading_id(module.key)),
                        html.Div(id=workflow_history_preview_meta_id(module.key)),
                        html.Div(id=workflow_history_preview_body_id(module.key)),
                        html.Div(
                            [
                                html.Button(
                                    'Cerrar',
                                    id=workflow_history_preview_close_id(module.key),
                                    n_clicks=0,
                                ),
                                html.Button(
                                    'Cargar como borrador',
                                    id=workflow_history_preview_load_id(module.key),
                                    n_clicks=0,
                                ),
                            ]
                        ),
                    ]
                ),
                id=workflow_history_preview_id(module.key),
                hidden=True,
            ),
        ]
    )


def _short(value: str | None) -> str:
    return value[:12] if value else '—'


def _format_datetime(value: datetime) -> str:
    return value.astimezone().strftime('%Y-%m-%d %H:%M:%S')


def _section_button_class(active: bool) -> str:
    base = 'atlanticus-manager__tab'
    return f'{base} {base}--active' if active else base


def _section_panel_class(active: bool) -> str:
    base = 'atlanticus-manager__section-panel'
    return f'{base} {base}--active' if active else base
