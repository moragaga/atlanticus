from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import dash_bootstrap_components as dbc
from dash import Input, Output, State, ctx, dcc, html, no_update

from atlanticus.web.modules import WebModule
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.recovery import UsersRecoveryConflictError
from atlanticus.web.users.web.projection_workflow import UsersProjectionWorkflow

_LOGGER = logging.getLogger(__name__)
_PREFIX = 'atlanticus-users-projection'
_CLOSED = f'{_PREFIX}__modal'
_OPEN = f'{_CLOSED} {_CLOSED}--open'


def _id(suffix: str) -> str:
    return f'{_PREFIX}__{suffix}'


@dataclass(frozen=True, slots=True)
class UsersProjectionWebContext:
    workflow: UsersProjectionWorkflow
    can_manage: Callable[[], bool]


def build_users_projection_configuration(context: UsersProjectionWebContext) -> object:
    permitted = context.can_manage()
    return html.Div(
        [
            dcc.Store(id=_id('active-tab'), data='capture', storage_type='memory'),
            dcc.Store(id=_id('capture-preview'), storage_type='memory'),
            dcc.Store(id=_id('capture-finished'), storage_type='memory'),
            dcc.Store(id=_id('inspection'), storage_type='memory'),
            dcc.Store(id=_id('apply-finished'), storage_type='memory'),
            dcc.Store(id=_id('pending-action'), storage_type='memory'),
            html.Nav(
                [
                    html.Button('Crear respaldo', id=_id('capture-tab'), n_clicks=0,
                                type='button', className=_tab_class(True)),
                    html.Button('Proyectar usuarios', id=_id('apply-tab'), n_clicks=0,
                                type='button', className=_tab_class(False)),
                ],
                className=f'{_PREFIX}__tabs',
                **{'aria-label': 'Procesos de proyección de usuarios'},
            ),
            html.Div(
                [
                    _section(
                        'Crear respaldo de usuarios',
                        'Guarda el conjunto de usuarios ya aprobados. No incorpora candidatos '
                        'pendientes ni modifica los usuarios actuales.',
                        [
                            _step('1', 'Revisar usuarios actuales',
                                  'Comprueba qué usuarios aprobados se incluirán en el respaldo.'),
                            _button('Revisar usuarios', 'preview-button', permitted=permitted),
                            html.Div(
                                _empty('Todavía no has revisado los usuarios actuales.'),
                                id=_id('capture-preview-panel'),
                                className=f'{_PREFIX}__result',
                            ),
                        ],
                    ),
                    _section(
                        'Guardar respaldo',
                        'Se generará un respaldo inmutable que podrás consultar y seleccionar '
                        'posteriormente desde «Proyectar usuarios».',
                        [
                            _field(
                                'Referencia de aprobación',
                                dbc.Input(id=_id('capture-reference'),
                                          placeholder='Ej.: solicitud o ticket aprobado',
                                          disabled=not permitted),
                                'Identifica la autorización o el motivo de esta captura.',
                            ),
                            _button('Revisar y guardar respaldo', 'open-capture',
                                    permitted=False),
                            html.Div(id=_id('capture-result'),
                                     className=f'{_PREFIX}__result', role='status'),
                        ],
                    ),
                ],
                id=_id('capture-panel'),
                className=_panel_class(True),
            ),
            html.Div(
                [
                    _section(
                        'Elegir respaldo aprobado',
                        'Selecciona una captura histórica. Elegirla no cambia los usuarios: '
                        'primero debes compararla con el estado actual.',
                        [
                            _field(
                                'Respaldo que se utilizará como referencia',
                                dcc.Dropdown(
                                    id=_id('snapshot-select'),
                                    options=[],
                                    placeholder='Seleccionar un respaldo',
                                    clearable=False,
                                    searchable=True,
                                    disabled=not permitted,
                                    className=f'{_PREFIX}__select',
                                ),
                                'El selector muestra la fecha de guardado. Al elegir verás el origen '
                                'y la referencia antes de comparar.',
                            ),
                            html.Div(
                                _empty('Elige un respaldo para conocer su fecha, origen y aprobación.'),
                                id=_id('selected-summary'),
                                className=f'{_PREFIX}__result',
                            ),
                            html.Div(
                                [
                                    _button('Actualizar respaldos', 'refresh-history',
                                            permitted=permitted, secondary=True),
                                    _button('Comparar con usuarios actuales', 'inspect-button',
                                            permitted=False),
                                ],
                                className=f'{_PREFIX}__actions',
                            ),
                            html.Div(id=_id('history-error'),
                                     className=f'{_PREFIX}__result', role='status'),
                        ],
                    ),
                    _section(
                        'Resultado de la comparación',
                        'Revisa las diferencias antes de elegir cómo aplicarlas.',
                        [
                            html.Div(
                                _empty('Selecciona un respaldo y pulsa «Comparar con usuarios actuales».'),
                                id=_id('inspection-panel'),
                                className=f'{_PREFIX}__result',
                            ),
                        ],
                    ),
                    _section(
                        'Aplicar el respaldo',
                        'Ambas operaciones requieren revisar los cambios y confirmar la '
                        'intervención. Si no hay diferencias, no se realizará ninguna escritura.',
                        [
                            html.Div(
                                [
                                    html.Span('¿Qué necesitas hacer?',
                                              className=f'{_PREFIX}__label'),
                                    dcc.RadioItems(
                                        id=_id('mode'),
                                        options=_mode_options(False, False),
                                        value='restore',
                                        className=f'{_PREFIX}__choices',
                                    ),
                                ],
                                className=f'{_PREFIX}__field',
                            ),
                            html.Div(id=_id('mode-help'),
                                     className=f'{_PREFIX}__help', role='status'),
                            _field(
                                'Referencia de aprobación',
                                dbc.Input(id=_id('apply-reference'),
                                          placeholder='Ej.: solicitud o ticket aprobado',
                                          disabled=not permitted),
                                'Debe identificar la autorización para esta operación.',
                            ),
                            _button('Revisar antes de aplicar', 'open-apply', permitted=False),
                            html.Div(id=_id('apply-result'),
                                     className=f'{_PREFIX}__result', role='status'),
                        ],
                    ),
                ],
                id=_id('apply-panel'),
                className=_panel_class(False),
            ),
            html.Div(
                [
                    html.Button('Cerrar', id=_id('modal-backdrop'),
                                n_clicks=0, className=f'{_PREFIX}__modal-backdrop',
                                type='button', **{'aria-label': 'Cancelar operación'}),
                    html.Section(
                        [
                            html.Header(
                                [
                                    html.H3(id=_id('modal-title')),
                                    html.Button('×', id=_id('modal-close'), n_clicks=0,
                                                type='button',
                                                className=f'{_PREFIX}__modal-close',
                                                **{'aria-label': 'Cerrar confirmación'}),
                                ],
                                className=f'{_PREFIX}__modal-header',
                            ),
                            html.Div(
                                [
                                    html.Div(id=_id('modal-content')),
                                    dcc.Checklist(id=_id('modal-checks'), options=[], value=[],
                                                  className=f'{_PREFIX}__checks'),
                                    html.Div(id=_id('modal-error'), role='alert'),
                                ],
                                className=f'{_PREFIX}__modal-body',
                            ),
                            html.Footer(
                                [
                                    _button('Cancelar', 'modal-cancel', permitted=permitted,
                                            secondary=True),
                                    _button('Confirmar', 'modal-confirm', permitted=permitted),
                                ],
                                className=f'{_PREFIX}__modal-actions',
                            ),
                        ],
                        className=f'{_PREFIX}__modal-card',
                        role='dialog',
                        **{'aria-modal': 'true', 'aria-label': 'Confirmar operación de usuarios'},
                    ),
                ],
                id=_id('modal'),
                className=_CLOSED,
            ),
        ],
        className=f'{_PREFIX} atlanticus-bootstrap',
    )


def _section(title: str, copy: str, children: list[object]) -> object:
    return html.Section(
        [
            html.Div([html.H3(title), html.P(copy)], className=f'{_PREFIX}__section-copy'),
            *children,
        ],
        className=f'{_PREFIX}__section',
    )


def _step(number: str, title: str, copy: str) -> object:
    return html.Div(
        [html.Span(number, className=f'{_PREFIX}__step-number'),
         html.Div([html.Strong(title), html.P(copy)])],
        className=f'{_PREFIX}__step',
    )


def _button(
    text: str, suffix: str, *, permitted: bool, secondary: bool = False
) -> object:
    variant = 'secondary' if secondary else 'primary'
    return html.Button(
        text,
        id=_id(suffix),
        n_clicks=0,
        type='button',
        disabled=not permitted,
        className=f'{_PREFIX}__button {_PREFIX}__button--{variant}',
    )


def _field(label: str, control: object, help_text: str) -> object:
    return html.Div(
        [html.Span(label, className=f'{_PREFIX}__label'),
         control, html.Small(help_text, className=f'{_PREFIX}__help')],
        className=f'{_PREFIX}__field',
    )


def _tab_class(active: bool) -> str:
    base = f'{_PREFIX}__tab'
    return f'{base} {base}--active' if active else base


def _panel_class(active: bool) -> str:
    base = f'{_PREFIX}__panel'
    return f'{base} {base}--active' if active else base


def _empty(message: str) -> object:
    return html.Div(message, className=f'{_PREFIX}__empty')


def create_users_projection_web_module(context: UsersProjectionWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_users_projection_callbacks(app, context)

    return WebModule(name='atlanticus-users-projection', register_callbacks=register_callbacks)


def register_users_projection_callbacks(app: object, context: UsersProjectionWebContext) -> None:
    @app.callback(
        Output(_id('active-tab'), 'data'),
        Output(_id('capture-tab'), 'className'),
        Output(_id('apply-tab'), 'className'),
        Output(_id('capture-panel'), 'className'),
        Output(_id('apply-panel'), 'className'),
        Input(_id('capture-tab'), 'n_clicks'),
        Input(_id('apply-tab'), 'n_clicks'),
        State(_id('active-tab'), 'data'),
    )
    def switch_tab(_capture, _apply, current):
        selected = current if current in {'capture', 'apply'} else 'capture'
        if ctx.triggered_id == _id('capture-tab'):
            selected = 'capture'
        elif ctx.triggered_id == _id('apply-tab'):
            selected = 'apply'
        capturing = selected == 'capture'
        return (selected, _tab_class(capturing), _tab_class(not capturing),
                _panel_class(capturing), _panel_class(not capturing))

    @app.callback(
        Output(_id('snapshot-select'), 'options'),
        Output(_id('history-error'), 'children'),
        Input(_id('refresh-history'), 'n_clicks'),
        Input(_id('capture-finished'), 'data'),
    )
    def history(_refresh, _captured):
        if not context.can_manage():
            return [], _error('No tienes autorización para consultar los respaldos.')
        try:
            options = [
                {'label': _snapshot_option(item), 'value': item['snapshot_id']}
                for item in context.workflow.history_details()
            ]
            return options, None if options else _empty('No hay respaldos aprobados disponibles.')
        except Exception:
            _LOGGER.exception('Could not list Users snapshots')
            return [], _error('No se pudo obtener el historial de respaldos.')

    @app.callback(
        Output(_id('selected-summary'), 'children'),
        Input(_id('snapshot-select'), 'value'),
    )
    def selected_summary(snapshot_id):
        if not isinstance(snapshot_id, str) or not snapshot_id:
            return _empty('Elige un respaldo para conocer su fecha, origen y aprobación.')
        if not context.can_manage():
            return _error('No tienes autorización para consultar este respaldo.')
        try:
            info = context.workflow.describe_snapshot(snapshot_id)
        except (UsersDefinitionError, UsersRecoveryConflictError) as error:
            return _error('No se pudieron leer los detalles del respaldo.', error)
        except Exception:
            _LOGGER.exception('Could not read selected Users snapshot')
            return _error('No se pudieron leer los detalles del respaldo.')
        return html.Div([
            html.Strong('Datos del respaldo elegido'),
            _facts((
                ('Fecha de captura', _format_timestamp(info['captured_at_utc'])),
                ('Usuarios aprobados', info['approved_count']),
            )),
            html.P(f"Ambiente de origen: {info['origin_environment']}"),
            html.P(f"Referencia de aprobación: {info['approval_reference']}"),
            _technical('Identificador completo', info['snapshot_id']),
        ], className=f'{_PREFIX}__summary')

    @app.callback(
        Output(_id('capture-preview'), 'data'),
        Output(_id('capture-preview-panel'), 'children'),
        Input(_id('preview-button'), 'n_clicks'),
        prevent_initial_call=True,
    )
    def preview_capture(clicks):
        if not clicks or not context.can_manage():
            return no_update, _error('No tienes autorización para revisar estos usuarios.')
        try:
            preview = context.workflow.preview_capture()
            return preview, html.Div(
                [
                    html.Strong('Usuarios incluidos en el respaldo'),
                    _facts((('Aprobados', len(preview['approved_ids'])),
                            ('Candidatos excluidos', len(preview['candidate_ids'])))),
                    html.Small('La revisión no crea ni modifica respaldos.'),
                    _technical('Identificador de contenido', preview['digest']),
                ],
                className=f'{_PREFIX}__summary',
            )
        except (UsersDefinitionError, UsersRecoveryConflictError) as error:
            return None, _error('No se pudieron revisar los usuarios.', error)
        except Exception:
            _LOGGER.exception('Users capture preview failed')
            return None, _error('No se pudieron revisar los usuarios.')

    @app.callback(
        Output(_id('open-capture'), 'disabled'),
        Input(_id('capture-preview'), 'data'),
        Input(_id('capture-reference'), 'value'),
    )
    def capture_ready(preview, reference):
        return (not context.can_manage() or not isinstance(preview, dict)
                or not _valid_reference(reference))

    @app.callback(
        Output(_id('inspection'), 'data'),
        Output(_id('inspection-panel'), 'children'),
        Input(_id('inspect-button'), 'n_clicks'),
        Input(_id('snapshot-select'), 'value'),
        Input(_id('refresh-history'), 'n_clicks'),
        Input(_id('capture-finished'), 'data'),
        Input(_id('apply-finished'), 'data'),
        prevent_initial_call=True,
    )
    def inspect(clicks, snapshot_id, _refresh, _capture, _apply):
        if ctx.triggered_id != _id('inspect-button'):
            return None, _empty('Selecciona un respaldo y pulsa «Comparar con usuarios actuales».')
        if not clicks or not context.can_manage():
            return None, _error('No tienes autorización para comparar respaldos.')
        if not isinstance(snapshot_id, str) or not snapshot_id:
            return None, _error('Primero selecciona el respaldo que deseas comparar.')
        try:
            result = context.workflow.inspect(snapshot_id)
            return result, _render_inspection(result)
        except (UsersDefinitionError, UsersRecoveryConflictError) as error:
            return None, _error('No se pudo comparar el respaldo.', error)
        except Exception:
            _LOGGER.exception('Users comparison failed')
            return None, _error('No se pudo comparar el respaldo.')

    @app.callback(
        Output(_id('inspect-button'), 'disabled'),
        Input(_id('snapshot-select'), 'value'),
    )
    def inspect_ready(snapshot_id):
        return not context.can_manage() or not isinstance(snapshot_id, str) or not snapshot_id

    @app.callback(
        Output(_id('mode'), 'options'),
        Output(_id('mode'), 'value'),
        Input(_id('inspection'), 'data'),
        State(_id('mode'), 'value'),
    )
    def modes(inspection, selected):
        if not isinstance(inspection, dict) or not _has_changes(inspection):
            return _mode_options(False, False), 'restore'
        can_restore = bool(inspection.get('can_restore'))
        can_replace = bool(inspection.get('can_replace'))
        selected = selected if (selected == 'restore' and can_restore) or (
            selected == 'replace' and can_replace
        ) else ('restore' if can_restore else 'replace')
        return _mode_options(can_restore, can_replace), selected

    @app.callback(
        Output(_id('mode-help'), 'children'),
        Output(_id('open-apply'), 'disabled'),
        Input(_id('mode'), 'value'),
        Input(_id('inspection'), 'data'),
        Input(_id('snapshot-select'), 'value'),
        Input(_id('apply-reference'), 'value'),
    )
    def apply_ready(mode, inspection, selected, reference):
        if not context.can_manage() or not isinstance(inspection, dict) or (
            inspection.get('snapshot_id') != selected
        ):
            return 'Compara primero el respaldo seleccionado.', True
        if not _has_changes(inspection):
            return 'Los usuarios ya coinciden con el respaldo. No es necesario aplicar cambios.', True
        if mode == 'restore':
            return (
                'Solo agregará usuarios aprobados faltantes; conserva todos los demás.'
                if inspection.get('can_restore') else
                'La restauración está bloqueada: existen diferencias que no se resuelven añadiendo usuarios.',
                not inspection.get('can_restore') or not _valid_reference(reference),
            )
        if mode == 'replace':
            return (
                'Sustituirá el conjunto actual: puede modificar y eliminar usuarios y descartar candidatos.'
                if inspection.get('can_replace') else
                'La sustitución está bloqueada: revisa las identidades y los perfiles incompatibles.',
                not inspection.get('can_replace') or not _valid_reference(reference),
            )
        return 'Selecciona una operación válida.', True

    @app.callback(
        Output(_id('modal'), 'className'),
        Output(_id('modal-title'), 'children'),
        Output(_id('modal-content'), 'children'),
        Output(_id('modal-confirm'), 'children'),
        Output(_id('pending-action'), 'data'),
        Output(_id('modal-checks'), 'options'),
        Output(_id('modal-checks'), 'value'),
        Output(_id('modal-error'), 'children'),
        Input(_id('open-capture'), 'n_clicks'),
        Input(_id('open-apply'), 'n_clicks'),
        Input(_id('modal-cancel'), 'n_clicks'),
        Input(_id('modal-close'), 'n_clicks'),
        Input(_id('modal-backdrop'), 'n_clicks'),
        State(_id('capture-preview'), 'data'),
        State(_id('capture-reference'), 'value'),
        State(_id('inspection'), 'data'),
        State(_id('snapshot-select'), 'value'),
        State(_id('mode'), 'value'),
        State(_id('apply-reference'), 'value'),
        prevent_initial_call=True,
    )
    def modal(_capture, _apply, _cancel, _close, _backdrop,
              preview, capture_ref, inspection, snapshot_id, mode, apply_ref):
        defaults = (_CLOSED, '', '', 'Confirmar', None, [], [], None)
        triggered = ctx.triggered_id
        if triggered in {_id('modal-cancel'), _id('modal-close'), _id('modal-backdrop')}:
            return defaults
        if not context.can_manage():
            return (*defaults[:7], _error('No tienes autorización para esta operación.'))
        if triggered == _id('open-capture'):
            if not isinstance(preview, dict) or not _valid_reference(capture_ref):
                return (_OPEN, 'Faltan datos', html.P('Revisa los usuarios e indica una referencia de aprobación.'),
                        'Confirmar', None, [], [], None)
            return (
                _OPEN,
                'Confirmar nuevo respaldo',
                html.Div([
                    html.P('Se guardará una captura inmutable de los usuarios aprobados.'),
                    _facts((('Usuarios aprobados', len(preview['approved_ids'])),
                            ('Candidatos no incluidos', len(preview['candidate_ids'])))),
                    html.P('No se modificarán los usuarios actuales.'),
                    html.P(f'Referencia: {capture_ref.strip()}', className=f'{_PREFIX}__modal-reference'),
                ]),
                'Guardar respaldo',
                {'action': 'capture', 'preview': preview, 'reference': capture_ref.strip()},
                [], [], None,
            )
        if triggered == _id('open-apply'):
            if (not isinstance(inspection, dict)
                    or inspection.get('snapshot_id') != snapshot_id
                    or mode not in {'restore', 'replace'}
                    or not inspection.get('can_restore' if mode == 'restore' else 'can_replace')
                    or not _has_changes(inspection)
                    or not _valid_reference(apply_ref)):
                return (_OPEN, 'Faltan datos', html.P('Compara el respaldo y completa la referencia antes de continuar.'),
                        'Confirmar', None, [], [], None)
            summary = (
                [('Agregar', len(inspection['create_ids']))]
                if mode == 'restore'
                else [
                    ('Agregar', len(inspection['create_ids'])),
                    ('Modificar', len(inspection['update_ids'])),
                    ('Eliminar', len(inspection['delete_ids'])),
                    ('Descartar candidatos', len(inspection['discarded_candidate_ids'])),
                ]
            )
            replace = mode == 'replace'
            return (
                _OPEN,
                'Confirmar sustitución de usuarios' if replace else 'Confirmar restauración de faltantes',
                html.Div([
                    html.P('El respaldo seleccionado será la autoridad para el conjunto completo.'
                           if replace else 'Solo se crearán los usuarios aprobados que aún no existan.'),
                    _facts(summary),
                    html.P('Esta operación puede eliminar usuarios y descartar candidatos.'
                           if replace else 'No se modificarán ni eliminarán usuarios existentes.',
                           className=f'{_PREFIX}__warning' if replace else ''),
                    html.P('Estas confirmaciones no activan mantenimiento ni revocan sesiones de forma automática.',
                           className=f'{_PREFIX}__warning'),
                    html.P(f'Referencia: {apply_ref.strip()}', className=f'{_PREFIX}__modal-reference'),
                ]),
                'Confirmar sustitución' if replace else 'Confirmar restauración',
                {'action': 'apply', 'inspection': inspection, 'snapshot_id': snapshot_id,
                 'mode': mode, 'reference': apply_ref.strip()},
                [
                    {'label': 'Confirmo que el ambiente está en mantenimiento',
                     'value': 'maintenance'},
                    {'label': 'Revisé las sesiones y revocaciones necesarias',
                     'value': 'revocations'},
                ],
                [], None,
            )
        return defaults

    @app.callback(
        Output(_id('modal'), 'className', allow_duplicate=True),
        Output(_id('pending-action'), 'data', allow_duplicate=True),
        Output(_id('modal-error'), 'children', allow_duplicate=True),
        Output(_id('capture-result'), 'children'),
        Output(_id('capture-preview'), 'data', allow_duplicate=True),
        Output(_id('capture-finished'), 'data'),
        Output(_id('apply-result'), 'children'),
        Output(_id('apply-finished'), 'data'),
        Output(_id('capture-reference'), 'value'),
        Input(_id('modal-confirm'), 'n_clicks'),
        State(_id('pending-action'), 'data'),
        State(_id('modal-checks'), 'value'),
        prevent_initial_call=True,
        running=[(Output(_id('modal-confirm'), 'disabled'), True, False)],
    )
    def confirm(clicks, action, confirmations):
        no_result = (no_update, no_update, no_update, no_update, no_update,
                     no_update, no_update, no_update, no_update)
        if not clicks or not isinstance(action, dict):
            return no_result
        if not context.can_manage():
            return (_CLOSED, None, no_update, _error('Acceso denegado.'),
                    no_update, no_update, no_update, no_update, no_update)
        if action['action'] == 'capture':
            try:
                saved = context.workflow.capture(action['preview'], action['reference'])
                return (_CLOSED, None, None,
                        _notice(f"Respaldo creado correctamente. Usuarios aprobados: {saved['approved_count']}."),
                        None, saved['snapshot_id'], no_update, no_update, '')
            except (UsersDefinitionError, UsersRecoveryConflictError) as error:
                return (_CLOSED, None, None,
                        _error('No se guardó el respaldo. Revisa nuevamente el estado.', error),
                        None, no_update, no_update, no_update, no_update)
            except Exception:
                _LOGGER.exception('Users capture failed')
                return (_CLOSED, None, None,
                        _error('No se guardó el respaldo. Revisa nuevamente el estado.'),
                        None, no_update, no_update, no_update, no_update)
        if action['action'] != 'apply':
            return no_result
        selected = set(confirmations or [])
        if not {'maintenance', 'revocations'} <= selected:
            return (no_update, no_update,
                    _error('Confirma el mantenimiento y la revisión de sesiones antes de continuar.'),
                    no_update, no_update, no_update, no_update, no_update, no_update)
        try:
            result = context.workflow.apply(
                inspection=action['inspection'],
                mode=action['mode'],
                approval_reference=action['reference'],
                maintenance_confirmed=True,
                revocations_reviewed=True,
                confirmed=True,
            )
            return (
                _CLOSED, None, None, no_update, no_update, no_update,
                _notice(
                    f"Usuarios actualizados según el respaldo. Agregados: {result['created']}; "
                    f"modificados: {result['updated']}; eliminados: {result['deleted']}. "
                    'Compara de nuevo antes de realizar otra operación.'
                ),
                result['operation_id'], no_update,
            )
        except (UsersDefinitionError, UsersRecoveryConflictError) as error:
            return (_CLOSED, None, None, no_update, no_update, no_update,
                    _error('La operación no se completó. Revisa la auditoría antes de reintentar.', error),
                    uuid4().hex, no_update)
        except Exception:
            _LOGGER.exception('Users projection failed')
            return (_CLOSED, None, None, no_update, no_update, no_update,
                    _error('La operación no se completó. Revisa la auditoría antes de reintentar.'),
                    uuid4().hex, no_update)


def _mode_options(can_restore: bool, can_replace: bool) -> list[dict[str, object]]:
    return [
        {'label': html.Div([
            html.Strong('Restaurar usuarios faltantes'),
            html.Span('Agrega solo aprobados que no existan; conserva todos los demás.'),
        ]), 'value': 'restore', 'disabled': not can_restore},
        {'label': html.Div([
            html.Strong('Sustituir usuarios por el respaldo'),
            html.Span('Iguala el conjunto completo; puede modificar, eliminar y descartar candidatos.'),
        ]), 'value': 'replace', 'disabled': not can_replace},
    ]


def _has_changes(inspection: dict[str, object]) -> bool:
    return any((inspection.get('create_ids'), inspection.get('update_ids'),
                inspection.get('delete_ids'), inspection.get('registry_write_required'),
                inspection.get('differences')))


def _valid_reference(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _render_inspection(document: dict[str, object]) -> object:
    differences = list(document['differences'])
    differences.extend(
        {'user_id': user_id, 'kind': 'discarded_candidate', 'fields': []}
        for user_id in document['discarded_candidate_ids']
    )
    difference_labels = {
        'missing': 'Usuario faltante',
        'different': 'Datos diferentes',
        'unexpected': 'Usuario no incluido',
        'identity_conflict': 'Identidad incompatible',
        'profile_unavailable': 'Perfil no disponible',
        'discarded_candidate': 'Candidato que se descartaría',
    }
    field_labels = {
        'enabled': 'Estado habilitado', 'profile_key': 'Perfil',
        'display_name': 'Nombre', 'email': 'Correo',
        'avatar_background_color': 'Color de avatar',
        'avatar_text_color': 'Color del texto',
        'issuer': 'Emisor de identidad', 'subject_id': 'ID del sujeto',
    }
    rows = [
        html.Tr([
            html.Td(item['user_id'], className=f'{_PREFIX}__identifier'),
            html.Td(difference_labels.get(item['kind'], item['kind'])),
            html.Td(', '.join(field_labels.get(field, field)
                              for field in item['fields']) or '—'),
        ])
        for item in differences
    ]
    state = document['registry_state']
    state_label = {'match': 'Coincide', 'conflict': 'Presenta diferencias',
                   'empty': 'Sin registro previo'}.get(state, state)
    return html.Div([
        html.Div([
            html.Strong('Respaldo seleccionado'),
            _facts((('Usuarios aprobados', document['approved_count']),
                    ('Registro actual', state_label))),
            html.P(f"Origen: {document['origin_environment']} · "
                   f"Captura: {_format_timestamp(document['captured_at_utc'])}",
                   className=f'{_PREFIX}__help'),
            _technical('Identificador del respaldo', document['snapshot_id']),
            _technical('Digest de verificación', document['snapshot_digest']),
        ], className=f'{_PREFIX}__summary'),
        html.Div([
            html.Strong('Cambios previstos para la sustitución completa'),
            _facts((('Agregar', len(document['create_ids'])),
                    ('Modificar', len(document['update_ids'])),
                    ('Eliminar', len(document['delete_ids'])),
                    ('Descartar candidatos', len(document['discarded_candidate_ids'])))),
            _empty('No se detectaron diferencias. No necesitas realizar ninguna operación.')
            if not _has_changes(document) else None,
        ], className=f'{_PREFIX}__summary'),
        html.Div([
            html.Strong('Detalle de diferencias'),
            html.Div(
                html.Table([
                    html.Thead(html.Tr([html.Th('Usuario'), html.Th('Diferencia'),
                                      html.Th('Campos afectados')])),
                    html.Tbody(rows or [html.Tr(html.Td('No hay diferencias', colSpan=3))]),
                ], className=f'{_PREFIX}__table'),
                className=f'{_PREFIX}__table-scroll',
            ),
        ], className=f'{_PREFIX}__summary'),
    ], className=f'{_PREFIX}__inspection')


def _snapshot_option(item: dict[str, str | None]) -> str:
    snapshot_id = item['snapshot_id']
    saved = item.get('saved_at_utc')
    date_label = 'Fecha no disponible'
    if saved:
        date_label = f'Guardado: {_format_timestamp(saved)}'
    return f'{date_label} · Respaldo {snapshot_id[:8]}… ({snapshot_id[-6:]})'


def _format_timestamp(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(UTC).strftime('%d/%m/%Y %H:%M UTC')


def _facts(items: object) -> object:
    return html.Div([
        html.Div([html.Strong(str(value)), html.Span(label)])
        for label, value in items
    ], className=f'{_PREFIX}__facts')


def _technical(label: str, value: str) -> object:
    return html.Details([
        html.Summary(label),
        html.Code(value, className=f'{_PREFIX}__identifier'),
    ], className=f'{_PREFIX}__technical')


def _notice(message: str) -> object:
    return html.Div(message, className=f'{_PREFIX}__notice {_PREFIX}__notice--success')


def _error(message: str, detail: Exception | None = None) -> object:
    return html.Div([
        html.Span(message),
        _technical('Detalle técnico', str(detail)) if detail is not None else None,
    ], className=f'{_PREFIX}__notice {_PREFIX}__notice--error')
