# Sustituye la carga histórica directa por una acción de inspección y un modal genérico de confirmación.
# Cerrar la vista previa no modifica el workspace; cargar como borrador sigue siendo una decisión explícita.

# Las acciones de conflicto reutilizan source_name para que Archivo local, SharePoint u otra fuente se muestren dinámicamente.
# Mantener el borrador es una decisión separada de publicar: la publicación sigue requiriendo una verificación posterior.

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from dash import dcc, html

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.coordinator import ManagerProjectionCoordinator
from atlanticus.web.manager.errors import ManagerError
from atlanticus.web.manager.models import (
    ManagerApplicationDefinition,
    ManagerBrand,
    ManagerBrandMark,
    ManagerModule,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.projection import (
    ManagerDraft,
    ProjectionIssue,
    ProjectionState,
    ProjectionStatus,
    ProjectionSummaryItem,
    RevisionHistoryEntry,
    SourceVerificationResult,
    resolve_projection_state,
)
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.ids import (
    CONTENT_ID,
    LOCATION_ID,
    REFRESH_BUTTON_ID,
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
    workflow_revision_id,
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
from atlanticus.web.services import ServiceRegistry

_STATE_LABELS = {
    ProjectionState.NO_SOURCE: 'Sin fuente',
    ProjectionState.SYNCHRONIZED: 'Actualizada',
    ProjectionState.READY: 'Lista',
    ProjectionState.UNAVAILABLE: 'No disponible',
}


def build_manager_header(
    *,
    definition: ManagerApplicationDefinition,
    services: ServiceRegistry,
) -> object:
    return html.Header(
        [
            _build_header_identity(
                definition.brand,
                title=definition.metadata.display_name,
                subtitle=definition.subtitle,
            ),
            html.Div(
                [
                    html.Button(
                        'Actualizar estados',
                        id=REFRESH_BUTTON_ID,
                        className='atlanticus-manager__button atlanticus-manager__button--header',
                    ),
                    definition.header_actions(services)
                    if definition.header_actions is not None
                    else None,
                ],
                className='atlanticus-manager__header-actions',
            ),
        ],
        className='atlanticus-manager__header',
    )


def build_manager_surface(
    *,
    definition: ManagerSurfaceDefinition,
    registry: ManagerModuleRegistry,
    services: ServiceRegistry,
    principal: ManagerPrincipal,
    authorization: ManagerAuthorizationPolicy,
) -> object:
    visible_modules = registry.visible_modules(principal, authorization)
    current_path = registry.route_for(registry.require(definition.default_module_key))
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
            *[
                dcc.Store(
                    id=workflow_refresh_signal_id(module.key),
                    data=0,
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            *[
                dcc.Store(
                    id=workflow_projection_signal_id(module.key),
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            # El workspace activo vive sólo en memoria: al recargar, Manager vuelve a hidratar desde Source.
            *[
                dcc.Store(
                    id=workflow_draft_id(module.key),
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            # El checkpoint explícitamente guardado sí persiste en el navegador, pero queda separado del editor.
            *[
                dcc.Store(
                    id=workflow_saved_draft_id(module.key),
                    storage_type='local',
                )
                for module in visible_modules
            ],
            *[
                dcc.Store(
                    id=workflow_validation_id(module.key),
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            *[
                dcc.Store(
                    id=workflow_source_verification_id(module.key),
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            *[
                dcc.Store(
                    id=workflow_editor_revision_id(module.key),
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            *[
                dcc.Store(
                    id=workflow_workspace_reset_signal_id(module.key),
                    data=0,
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            *[
                dcc.Store(
                    id=workflow_workspace_command_id(module.key),
                    storage_type='memory',
                )
                for module in visible_modules
            ],
            html.Section(id=SUMMARY_ID, className='atlanticus-manager__summary'),
            html.Button(
                '⚙',
                id=SIDEBAR_TOGGLE_ID,
                className='atlanticus-manager__sidebar-trigger',
                title='Abrir configuraciones',
                **{'aria-label': 'Abrir configuraciones'},
            ),
            html.Main(id=CONTENT_ID, className='atlanticus-manager__content'),
            html.Aside(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.Strong('Configuraciones'),
                                    html.Span('Selecciona el módulo que quieres administrar.'),
                                ]
                            ),
                            html.Button(
                                '×',
                                id=SIDEBAR_CLOSE_ID,
                                className='atlanticus-manager__icon-button',
                                title='Cerrar configuraciones',
                            ),
                        ],
                        className='atlanticus-manager__sidebar-header',
                    ),
                    html.Div(
                        id=SIDEBAR_MODULES_ID,
                        children=build_sidebar_modules(
                            registry=registry,
                            modules=visible_modules,
                            current_path=current_path,
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
                **{'aria-label': 'Cerrar configuraciones'},
            ),
        ],
        className='atlanticus-manager atlanticus-manager--surface',
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
            _summary_item('Total', str(total), 'Módulos disponibles'),
            _summary_item(
                'Actualizadas',
                str(synchronized),
                'Fuente y proyección sincronizadas',
            ),
            _summary_item(
                'Pendientes',
                str(pending),
                'Configuración sin fuente publicada',
            ),
            _summary_item('Listas', str(ready), 'Fuente publicada pendiente de proyección'),
            _summary_item(
                'Con errores',
                str(errors),
                'Validación rechazada o estado no disponible',
            ),
        ],
        className='atlanticus-manager__summary-items',
    )


def build_sidebar_modules(
    *,
    registry: ManagerModuleRegistry,
    modules: tuple[ManagerModule, ...],
    current_path: str,
    states: Mapping[str, ProjectionState],
) -> tuple[object, ...]:
    result: list[object] = []
    for group in registry.groups:
        group_modules = tuple(module for module in modules if module.group_key == group.key)
        if not group_modules:
            continue
        result.append(html.Div(group.title, className='atlanticus-manager__sidebar-group'))
        for module in group_modules:
            state = states.get(module.key, ProjectionState.UNAVAILABLE)
            class_name = 'atlanticus-manager__sidebar-link'
            module_route = registry.route_for(module)
            if module_route == current_path:
                class_name += ' atlanticus-manager__sidebar-link--active'
            result.append(
                dcc.Link(
                    [
                        html.Div(
                            [
                                html.Strong(module.title),
                                html.Span(module.description),
                            ]
                        ),
                        html.Span(
                            _STATE_LABELS[state],
                            className=(
                                'atlanticus-manager__state '
                                f'atlanticus-manager__state--{state.value}'
                            ),
                        ),
                    ],
                    href=module_route,
                    className=class_name,
                )
            )
    return tuple(result)


def build_module_content(
    *,
    module: ManagerModule,
    services: ServiceRegistry,
    coordinator: ManagerProjectionCoordinator,
    principal: ManagerPrincipal,
) -> object:
    try:
        status = coordinator.get_status(module.key, principal)
        history = coordinator.list_history(module.key, principal, limit=20)
        can_load_history = coordinator.can_load_history(module.key, principal)
    except ManagerError as error:
        status = None
        history = ()
        can_load_history = False
        status_error = str(error)
    except Exception:
        status = None
        history = ()
        can_load_history = False
        status_error = 'Configuration status could not be loaded'
    else:
        status_error = None

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
                build_workflow_panel(
                    module=module,
                    status=status,
                    history=history,
                    can_load_history=can_load_history,
                    error=status_error,
                ),
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
    history: tuple[RevisionHistoryEntry, ...],
    can_load_history: bool,
    error: str | None,
) -> object:
    return html.Div(
        [
            dcc.Store(
                id=workflow_revision_id(module.key),
                data=_workflow_revision_state(status),
            ),
            html.Div(
                id=workflow_draft_status_id(module.key),
                className='atlanticus-manager__workflow-status',
            ),
            html.Div(
                build_workflow_status_content(
                    module=module,
                    status=status,
                    error=error,
                ),
                id=workflow_status_id(module.key),
                className='atlanticus-manager__workflow-status',
            ),
            _build_workflow_actions(module, status),
            html.Div(id=workflow_result_id(module.key)),
            html.Div(
                build_workflow_history_content(
                    module=module,
                    status=status,
                    history=history,
                    can_load_history=can_load_history,
                    error=error,
                ),
                id=workflow_history_id(module.key),
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
        return html.Div(
            error,
            className='atlanticus-manager__message atlanticus-manager__message--error',
        )
    if status is None:
        return html.Div(
            'Configuration status is unavailable',
            className='atlanticus-manager__message atlanticus-manager__message--error',
        )
    state = resolve_projection_state(status)
    return html.Section(
        [
            _workflow_group_header(
                'Estado publicado',
                'Lo que ya existe en la fuente de verdad y en la proyección runtime.',
                state=state,
            ),
            html.Div(
                [
                    _workflow_stage_card(
                        step='4',
                        title='Fuente de verdad',
                        subtitle=module.source_name,
                        items=(
                            ('Revisión actual', _short_revision(status.source_revision)),
                            ('Última publicación', _audit_value(status.source_audit)),
                        ),
                    ),
                    _workflow_stage_card(
                        step='5',
                        title='Proyección runtime',
                        subtitle=module.projection_name,
                        items=(
                            (
                                'Revisión activa',
                                _short_revision(status.active_source_revision),
                            ),
                            ('Última proyección', _audit_value(status.projection_audit)),
                        ),
                    ),
                ],
                className='atlanticus-manager__workflow-stage-grid',
            ),
        ],
        className='atlanticus-manager__workflow-group',
    )


def build_workflow_draft_content(
    *,
    draft: ManagerDraft | None,
    validation: dict[str, object] | None,
    source_verification: SourceVerificationResult | None,
    editor_dirty: bool,
    principal: ManagerPrincipal,
    source_revision: str | None = None,
) -> object:
    if draft is None:
        return html.Section(
            [
                _workflow_group_header(
                    'Trabajo local',
                    'Todavía no hay un borrador guardado en este navegador.',
                ),
                html.Div(
                    'Guarda un borrador para poder validarlo antes de publicarlo.',
                    className='atlanticus-manager__workflow-empty',
                ),
            ],
            className='atlanticus-manager__workflow-group',
        )
    if draft.owner_subject_id != principal.subject_id:
        return html.Div(
            'El borrador local pertenece a otro usuario.',
            className='atlanticus-manager__message atlanticus-manager__message--error',
        )
    validation_matches_draft = bool(
        validation and validation.get('draft_revision') == draft.revision
    )
    current_validation = validation if validation_matches_draft else None
    valid = _draft_validation_is_current(draft, current_validation)
    validation_label = 'Validado' if valid else 'Pendiente'
    draft_state = (
        'Cambios sin guardar'
        if editor_dirty
        else ('Publicado' if draft.revision == source_revision else 'No publicado')
    )
    validated_by = '—'
    validated_at = '—'
    if current_validation is not None:
        if current_validation.get('valid') is False:
            validation_label = 'Con errores'
        validated_by = str(current_validation.get('validated_by') or '—')
        validated_at = _format_optional_datetime(current_validation.get('validated_at'))
    verification_label = 'No requerida' if draft.revision == source_revision else 'Pendiente'
    verification_revision = '—'
    verification_actor = '—'
    verification_at = '—'
    if source_verification is not None and source_verification.draft_revision == draft.revision:
        verification_label = 'Verificada' if source_verification.publishable else 'Conflicto'
        verification_revision = _short_revision(source_verification.source_revision)
        if source_verification.source_audit is not None:
            verification_actor = source_verification.source_audit.actor
        verification_at = _format_datetime(source_verification.checked_at)
    return html.Section(
        [
            _workflow_group_header(
                'Trabajo local',
                'Este estado vive en el navegador y todavía no modifica la fuente de verdad.',
            ),
            html.Div(
                [
                    _workflow_stage_card(
                        step='1',
                        title='Borrador del navegador',
                        subtitle=draft_state,
                        items=(
                            ('Revisión', _short_revision(draft.revision)),
                            ('Guardado', _format_datetime(draft.saved_at)),
                            ('Base fuente', _short_revision(draft.base_source_revision)),
                        ),
                    ),
                    _workflow_stage_card(
                        step='2',
                        title='Validación',
                        subtitle=validation_label,
                        items=(
                            ('Validado por', validated_by),
                            ('Fecha', validated_at),
                        ),
                    ),
                    _workflow_stage_card(
                        step='3',
                        title='Verificación de fuente',
                        subtitle=verification_label,
                        items=(
                            ('Revisión comprobada', verification_revision),
                            ('Actor fuente', verification_actor),
                            ('Verificada', verification_at),
                        ),
                    ),
                ],
                className='atlanticus-manager__workflow-stage-grid',
            ),
            _build_validation_issues(_validation_issues(current_validation)),
        ],
        className='atlanticus-manager__workflow-group',
    )


# Describe el checkpoint persistente sin convertirlo en workspace; también avisa si cambió la revisión de Source.
def build_saved_draft_content(
    *,
    draft: ManagerDraft | None,
    source_revision: str | None,
    incompatible: bool = False,
) -> object:
    if incompatible:
        return html.Div(
            'Hay un borrador guardado antiguo o incompatible. No se aplicará automáticamente; '
            'puedes descartarlo desde este navegador.',
            className='atlanticus-manager__message atlanticus-manager__message--notice',
        )
    if draft is None:
        return html.Div('No hay un borrador guardado para recuperar.')
    source_changed = draft.base_source_revision != source_revision
    details = [
        html.Span(
            [
                html.Small('Borrador guardado'),
                html.Code(_short_revision(draft.revision)),
            ]
        ),
        html.Span(
            [
                html.Small('Base fuente'),
                html.Code(_short_revision(draft.base_source_revision)),
            ]
        ),
    ]
    if source_changed:
        details.append(
            html.Span(
                [
                    html.Small('Fuente actual'),
                    html.Code(_short_revision(source_revision)),
                ]
            )
        )
    return html.Div(
        [
            html.Strong(
                'La fuente cambió desde que se guardó este borrador.'
                if source_changed
                else 'Hay un borrador guardado disponible.'
            ),
            html.P(
                'La configuración publicada se mantiene visible hasta que elijas recuperar '
                'este borrador.'
            ),
            html.Div(details, className='atlanticus-manager__conflict-revisions'),
        ],
        className=(
            'atlanticus-manager__message atlanticus-manager__message--notice'
            if source_changed
            else 'atlanticus-manager__workflow-empty'
        ),
    )


def build_source_conflict_content(
    *,
    draft: ManagerDraft,
    verification: SourceVerificationResult,
) -> object:
    actor = (
        verification.source_audit.actor if verification.source_audit is not None else 'Otro usuario'
    )
    occurred_at = (
        _format_datetime(verification.source_audit.occurred_at)
        if verification.source_audit is not None
        else '—'
    )
    return html.Div(
        [
            html.Strong('La fuente cambió mientras estabas trabajando.'),
            html.P(
                f'{actor} publicó una revisión nueva el {occurred_at}. '
                'Tu borrador se conserva sin cambios.'
            ),
            html.Div(
                [
                    html.Span(
                        [
                            html.Small('Base de tu borrador'),
                            html.Code(_short_revision(draft.base_source_revision)),
                        ]
                    ),
                    html.Span(
                        [
                            html.Small('Fuente actual'),
                            html.Code(_short_revision(verification.source_revision)),
                        ]
                    ),
                ],
                className='atlanticus-manager__conflict-revisions',
            ),
        ],
        className='atlanticus-manager__conflict-details',
    )


def build_workflow_history_content(
    *,
    module: ManagerModule,
    status: ProjectionStatus | None,
    history: tuple[RevisionHistoryEntry, ...],
    can_load_history: bool,
    error: str | None,
) -> object:
    if error is not None or status is None:
        return None
    return _build_history(
        history,
        module=module,
        can_load_history=can_load_history,
    )


def _workflow_revision_state(status: ProjectionStatus | None) -> dict[str, object] | None:
    if status is None:
        return None
    return {
        'source_revision': status.source_revision,
        'source_actor': status.source_audit.actor if status.source_audit is not None else None,
        'source_occurred_at': (
            status.source_audit.occurred_at.isoformat() if status.source_audit is not None else None
        ),
        'active_source_revision': status.active_source_revision,
    }


def _can_project(status: ProjectionStatus | None) -> bool:
    if status is None or status.source_revision is None:
        return False
    return status.active_source_revision != status.source_revision


def _build_header_identity(
    brand: ManagerBrand | None,
    *,
    title: str,
    subtitle: str,
) -> object:
    product = _brand_mark(brand, 'product')
    supporting = tuple(
        mark
        for role in ('framework', 'organization')
        if (mark := _brand_mark(brand, role)) is not None
    )
    return html.Div(
        [
            _build_brand_mark(product)
            if product is not None
            else html.Div('A', className='atlanticus-manager__brand-fallback'),
            html.Div(
                [html.H1(title), html.P(subtitle)],
                className='atlanticus-manager__title',
            ),
            html.Div(
                [_build_brand_mark(mark) for mark in supporting],
                className='atlanticus-manager__brand-supporting',
            )
            if supporting
            else None,
        ],
        className='atlanticus-manager__header-identity',
    )


def _brand_mark(brand: ManagerBrand | None, role: str) -> ManagerBrandMark | None:
    if brand is None:
        return None
    return next((mark for mark in brand.marks if mark.role == role), None)


def _build_brand_mark(mark: ManagerBrandMark) -> object:
    return html.Div(
        [
            html.Img(src=mark.logo_src, alt=mark.logo_alt),
            html.Div(
                [
                    html.Small(mark.eyebrow) if mark.eyebrow else None,
                    html.Span(mark.label) if mark.label else None,
                ]
            ),
        ],
        className=f'atlanticus-manager__brand-mark atlanticus-manager__brand-mark--{mark.role}',
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
        [
            html.Span(label, className='atlanticus-manager__summary-label'),
            html.Strong(value, className='atlanticus-manager__summary-value'),
            html.Small(detail, className='atlanticus-manager__summary-detail'),
        ],
        className='atlanticus-manager__summary-item',
    )


def _build_workflow_actions(
    module: ManagerModule,
    status: ProjectionStatus | None,
) -> object:
    return html.Div(
        [
            html.Section(
                [
                    _workflow_group_header(
                        'Workspace local',
                        'Controla el trabajo de este módulo sin modificar la fuente ni la proyección.',
                    ),
                    html.Div(
                        [
                            html.Button(
                                'Descartar cambios locales',
                                id=workflow_action_id(module.key, 'discard-local'),
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
                                disabled=True,
                            ),
                            html.Button(
                                'Recargar',
                                id=workflow_action_id(module.key, 'reload'),
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
                            ),
                        ],
                        className='atlanticus-manager__workspace-actions',
                    ),
                    # Recuperar y descartar son acciones explícitas; la presencia del checkpoint no modifica el editor.
                    html.Div(
                        id=workflow_saved_draft_status_id(module.key),
                        className='atlanticus-manager__workflow-empty',
                    ),
                    html.Div(
                        [
                            html.Button(
                                'Recuperar borrador',
                                id=workflow_action_id(module.key, 'recover-saved-draft'),
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
                                disabled=True,
                            ),
                            html.Button(
                                'Descartar borrador guardado',
                                id=workflow_action_id(module.key, 'discard-saved-draft'),
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
                                disabled=True,
                            ),
                        ],
                        className='atlanticus-manager__workspace-actions',
                    ),
                    html.P(
                        (
                            f'Recargar restaura la versión actual de {module.source_name} y vuelve '
                            'a consultar fuente, historial y proyección.'
                        ),
                        className='atlanticus-manager__workspace-help',
                    ),
                ],
                className='atlanticus-manager__workflow-group',
            ),
            html.Section(
                [
                    _workflow_group_header(
                        'Flujo de publicación',
                        'Avanza en orden: guardar, validar, verificar la fuente y publicar.',
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
                                        className=(
                                            'atlanticus-manager__button '
                                            'atlanticus-manager__button--secondary'
                                        ),
                                    ),
                                    html.Button(
                                        'Mantener mi borrador',
                                        id=workflow_action_id(module.key, 'keep-draft'),
                                        n_clicks=0,
                                        className=(
                                            'atlanticus-manager__button '
                                            'atlanticus-manager__button--secondary'
                                        ),
                                    ),
                                    html.Button(
                                        'Forzar publicación',
                                        id=workflow_action_id(module.key, 'force-publish'),
                                        n_clicks=0,
                                        className=(
                                            'atlanticus-manager__button '
                                            'atlanticus-manager__button--danger'
                                        ),
                                        disabled=True,
                                        hidden=not module.force_publish_enabled,
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
                            _workflow_action_step(
                                '1',
                                'Guardar borrador',
                                'Conserva el trabajo únicamente en este navegador.',
                                html.Button(
                                    'Guardar borrador',
                                    id=workflow_action_id(module.key, 'save-draft'),
                                    n_clicks=0,
                                    className=(
                                        'atlanticus-manager__button '
                                        'atlanticus-manager__button--secondary'
                                    ),
                                    disabled=True,
                                ),
                            ),
                            _workflow_action_step(
                                '2',
                                'Validar',
                                'Comprueba el borrador sin escribir en la fuente de verdad.',
                                html.Button(
                                    'Validar borrador',
                                    id=workflow_action_id(module.key, 'validate'),
                                    n_clicks=0,
                                    className=(
                                        'atlanticus-manager__button '
                                        'atlanticus-manager__button--secondary'
                                    ),
                                    disabled=True,
                                ),
                            ),
                            _workflow_action_step(
                                '3',
                                'Verificar fuente',
                                f'Comprueba que {module.source_name} siga en la revisión base del borrador.',
                                html.Button(
                                    f'Verificar {module.source_name}',
                                    id=workflow_action_id(module.key, 'verify-source'),
                                    n_clicks=0,
                                    className=(
                                        'atlanticus-manager__button '
                                        'atlanticus-manager__button--secondary'
                                    ),
                                    disabled=True,
                                ),
                            ),
                            _workflow_action_step(
                                '4',
                                'Publicar',
                                f'Guarda la revisión validada en {module.source_name}.',
                                html.Button(
                                    f'Guardar en {module.source_name}',
                                    id=workflow_action_id(module.key, 'publish'),
                                    n_clicks=0,
                                    className=(
                                        'atlanticus-manager__button '
                                        'atlanticus-manager__button--secondary'
                                    ),
                                    disabled=True,
                                ),
                            ),
                            _workflow_action_step(
                                '5',
                                'Proyectar',
                                f'Actualiza manualmente el runtime disponible en {module.projection_name}.',
                                html.Button(
                                    f'Proyectar en {module.projection_name}',
                                    id=workflow_action_id(module.key, 'project'),
                                    n_clicks=0,
                                    className=(
                                        'atlanticus-manager__button '
                                        'atlanticus-manager__button--primary'
                                    ),
                                    disabled=not _can_project(status),
                                ),
                            ),
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
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--secondary'
                            ),
                        ),
                        html.Button(
                            'Confirmar',
                            id=workflow_action_id(module.key, 'workspace-confirm'),
                            n_clicks=0,
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--danger'
                            ),
                        ),
                    ],
                    className='atlanticus-manager__workspace-confirm-actions',
                ),
            ],
            className='atlanticus-manager__workspace-confirm-card',
        ),
        id=workflow_workspace_confirmation_id(module.key),
        className='atlanticus-manager__workspace-confirm',
        hidden=True,
    )


def _workflow_action_step(
    step: str,
    title: str,
    description: str,
    action: object,
) -> object:
    return html.Article(
        [
            html.Div(
                [
                    html.Span(step, className='atlanticus-manager__workflow-step-number'),
                    html.Div(
                        [
                            html.Strong(title),
                            html.P(description),
                        ]
                    ),
                ],
                className='atlanticus-manager__workflow-step-heading',
            ),
            action,
        ],
        className='atlanticus-manager__workflow-action-step',
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
                className=(f'atlanticus-manager__state atlanticus-manager__state--{state.value}'),
            )
            if state is not None
            else None,
        ],
        className='atlanticus-manager__workflow-group-header',
    )


def _workflow_stage_card(
    *,
    step: str,
    title: str,
    subtitle: str,
    items: tuple[tuple[str, str], ...],
) -> object:
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


def _audit_value(audit) -> str:
    if audit is None:
        return 'Sin registro'
    return f'{audit.actor} · {_format_datetime(audit.occurred_at)}'


def _build_history(
    history: tuple[RevisionHistoryEntry, ...],
    *,
    module: ManagerModule,
    can_load_history: bool,
) -> object:
    rows = []
    for index, entry in enumerate(history):
        labels = []
        if entry.current:
            labels.append('Fuente actual')
        if entry.active:
            labels.append('Proyección activa')
        status = ' · '.join(labels) if labels else 'Histórica'
        action = None
        if can_load_history and module.history_preview_renderer is not None:
            action = html.Button(
                'Ver revisión',
                id=history_preview_open_id(
                    module.key,
                    entry.revision,
                    f'{index}-{entry.saved_at.isoformat()}',
                    saved_by=entry.saved_by,
                    saved_at=_format_datetime(entry.saved_at),
                    current=entry.current,
                    active=entry.active,
                ),
                n_clicks=0,
                className=(
                    'atlanticus-manager__button '
                    'atlanticus-manager__button--secondary '
                    'atlanticus-manager__history-preview-open'
                ),
            )
        rows.append(
            html.Div(
                [
                    html.Code(_short_revision(entry.revision)),
                    html.Span(entry.saved_by),
                    html.Time(_format_datetime(entry.saved_at)),
                    html.Span(status, className='atlanticus-manager__history-status'),
                    action,
                ],
                className='atlanticus-manager__history-row',
            )
        )
    header = html.Div(
        [
            html.Span('Revisión'),
            html.Span('Publicado por'),
            html.Span('Fecha'),
            html.Span('Estado'),
            html.Span('Acción'),
        ],
        className='atlanticus-manager__history-row atlanticus-manager__history-row--header',
    )
    return html.Section(
        [
            html.H3('Historial publicado'),
            html.P(
                'Solo aparecen revisiones publicadas en la fuente de verdad. '
                'Abre una revisión para inspeccionarla antes de cargarla como borrador local.'
            ),
            header if rows else None,
            html.Div(rows) if rows else html.Div('Sin revisiones históricas.'),
        ],
        className='atlanticus-manager__history',
    )


def _build_history_preview_shell(module: ManagerModule) -> object:
    return html.Div(
        [
            dcc.Store(
                id=workflow_history_preview_store_id(module.key),
                storage_type='memory',
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Header(
                                [
                                    html.Div(
                                        [
                                            html.P(
                                                'Vista previa histórica',
                                                className='atlanticus-manager__eyebrow',
                                            ),
                                            html.H3(
                                                id=workflow_history_preview_heading_id(module.key)
                                            ),
                                        ]
                                    ),
                                ],
                                className='atlanticus-manager__history-preview-header',
                            ),
                            html.Div(
                                id=workflow_history_preview_meta_id(module.key),
                                className='atlanticus-manager__history-preview-meta',
                            ),
                            html.Div(
                                id=workflow_history_preview_body_id(module.key),
                                className='atlanticus-manager__history-preview-body',
                            ),
                            html.P(
                                (
                                    'Cargar esta revisión reemplazará el trabajo local actual del '
                                    'módulo. La fuente de verdad y la proyección no se modificarán.'
                                ),
                                className='atlanticus-manager__history-preview-help',
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        'Cerrar',
                                        id=workflow_history_preview_close_id(module.key),
                                        n_clicks=0,
                                        className=(
                                            'atlanticus-manager__button '
                                            'atlanticus-manager__button--secondary'
                                        ),
                                    ),
                                    html.Button(
                                        'Cargar como borrador',
                                        id=workflow_history_preview_load_id(module.key),
                                        n_clicks=0,
                                        className='atlanticus-manager__button',
                                    ),
                                ],
                                className='atlanticus-manager__history-preview-actions',
                            ),
                        ],
                        className='atlanticus-manager__history-preview-card',
                        **{
                            'role': 'dialog',
                            'aria-modal': 'true',
                            'aria-label': f'Vista previa histórica de {module.title}',
                        },
                    )
                ],
                id=workflow_history_preview_id(module.key),
                hidden=True,
                className='atlanticus-manager__history-preview',
            ),
        ]
    )


def _draft_validation_is_current(
    draft: ManagerDraft,
    validation: dict[str, object] | None,
) -> bool:
    return bool(
        validation
        and validation.get('draft_revision') == draft.revision
        and validation.get('valid') is True
    )


def _validation_issues(
    validation: dict[str, object] | None,
) -> tuple[ProjectionIssue, ...]:
    if not validation:
        return ()
    raw = validation.get('issues')
    if not isinstance(raw, list):
        return ()
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            result.append(
                ProjectionIssue(
                    code=str(item['code']),
                    message=str(item['message']),
                    level=str(item.get('level', 'error')),
                    path=str(item['path']) if item.get('path') is not None else None,
                )
            )
        except KeyError, ValueError:
            continue
    return tuple(result)


def _build_validation_issues(issues: tuple[ProjectionIssue, ...]) -> object:
    if not issues:
        return None
    return html.Ul(
        [
            html.Li(
                f'{issue.path}: {issue.message}' if issue.path else issue.message,
                className=f'atlanticus-manager__issue atlanticus-manager__issue--{issue.level}',
            )
            for issue in issues
        ],
        className='atlanticus-manager__issues',
    )


def _build_summary_items(items: tuple[ProjectionSummaryItem, ...]) -> object:
    if not items:
        return None
    return html.Div(
        [html.Span(f'{item.label}: {item.value}') for item in items],
        className='atlanticus-manager__result-summary',
    )


def _short_revision(value: str | None) -> str:
    return value[:12] if value else '—'


def _format_datetime(value: datetime) -> str:
    return value.astimezone().strftime('%Y-%m-%d %H:%M:%S')


def _format_optional_datetime(value: object) -> str:
    if value is None:
        return '—'
    try:
        return _format_datetime(datetime.fromisoformat(str(value)))
    except ValueError:
        return '—'


def _section_button_class(active: bool) -> str:
    base = 'atlanticus-manager__tab'
    return f'{base} {base}--active' if active else base


def _section_panel_class(active: bool) -> str:
    base = 'atlanticus-manager__section-panel'
    return f'{base} {base}--active' if active else base
