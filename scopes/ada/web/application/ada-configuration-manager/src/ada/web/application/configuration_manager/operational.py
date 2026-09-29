from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dash import Input, Output, State, dcc, html, no_update

from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
    assignment_source_key,
)
from atlanticus.web.manager import ManagerEntry, ManagerPrincipal
from atlanticus.web.modules import WebModule
from atlanticus.web.source.models import SourceSnapshot
from atlanticus.web.users.models import UserRecord

OPERATIONAL_MANAGER_ACCESS_KEY = 'operational.manage'
_PREFIX = 'ada-operational-manager'
_USER = f'{_PREFIX}-user'
_AREA = f'{_PREFIX}-area'
_POSITION = f'{_PREFIX}-position'
_GROUP = f'{_PREFIX}-group'
_ASSIGNMENT_REVISION = f'{_PREFIX}-assignment-revision'
_ASSIGNMENT_SAVE = f'{_PREFIX}-assignment-save'
_ASSIGNMENT_REPROJECT = f'{_PREFIX}-assignment-reproject'
_ASSIGNMENT_RESULT = f'{_PREFIX}-assignment-result'
_POSITION_SELECT = f'{_PREFIX}-position-select'
_POSITION_ID = f'{_PREFIX}-position-id'
_POSITION_LABEL = f'{_PREFIX}-position-label'
_POSITION_ACTIVE = f'{_PREFIX}-position-active'
_CATALOG_REVISION = f'{_PREFIX}-catalog-revision'
_CATALOG_SAVE = f'{_PREFIX}-catalog-save'
_CATALOG_REPROJECT = f'{_PREFIX}-catalog-reproject'
_CATALOG_RESULT = f'{_PREFIX}-catalog-result'


@dataclass(frozen=True, slots=True)
class OperationalManagerContext:
    service: OperationalIdentificationService
    promoted_users: Callable[[], tuple[UserRecord, ...]]
    principal: Callable[[], ManagerPrincipal]

    def can_manage(self) -> bool:
        return OPERATIONAL_MANAGER_ACCESS_KEY in self.principal().access_keys


def create_operational_manager_entry(context: OperationalManagerContext) -> ManagerEntry:
    return ManagerEntry(
        key='operational-identification',
        group_key='administration',
        title='Datos operacionales',
        route='/operational-identification',
        order=15,
        description='Cargos y asignaciones operacionales de usuarios promovidos.',
        layout=lambda _services: build_operational_manager_layout(context),
        access_key=OPERATIONAL_MANAGER_ACCESS_KEY,
        web_module=WebModule(
            name='ada-operational-identification-manager',
            register_callbacks=lambda app, _services: register_operational_callbacks(app, context),
        ),
    )


def build_operational_manager_layout(context: OperationalManagerContext):
    if not context.can_manage():
        return html.P('No tienes acceso a esta configuración.')
    try:
        catalog_snapshot, catalog = context.service.catalog_for_edit()
        users = context.promoted_users()
    except Exception:
        return html.P('No fue posible cargar los datos operacionales.')
    options = _position_options(catalog)
    return html.Div(
        [
            html.H3('Datos operacionales'),
            html.P('Asigna cargo, área y grupo a usuarios promovidos. Todos son opcionales.'),
            dcc.Tabs(
                value='assignments',
                children=[
                    dcc.Tab(
                        label='Asignaciones',
                        value='assignments',
                        children=[
                            html.Label('Usuario'),
                            dcc.Dropdown(
                                id=_USER,
                                options=[
                                    {
                                        'label': f'{user.display_name} ({user.user_id})',
                                        'value': user.user_id,
                                    }
                                    for user in users
                                ],
                                placeholder='Seleccionar usuario promovido',
                                clearable=True,
                            ),
                            dcc.Store(id=_ASSIGNMENT_REVISION),
                            html.Label('Área'),
                            dcc.Dropdown(
                                id=_AREA,
                                options=[
                                    {'label': 'Mina', 'value': 'mina'},
                                    {'label': 'Planta', 'value': 'planta'},
                                ],
                                placeholder='Sin información',
                                clearable=True,
                            ),
                            html.Label('Cargo'),
                            dcc.Dropdown(
                                id=_POSITION,
                                options=options,
                                placeholder='Sin información',
                                clearable=True,
                            ),
                            html.Label('Grupo'),
                            dcc.Dropdown(
                                id=_GROUP,
                                options=[
                                    {'label': f'Grupo {number}', 'value': number}
                                    for number in range(1, 5)
                                ],
                                placeholder='Sin información',
                                clearable=True,
                            ),
                            html.Button('Guardar asignación', id=_ASSIGNMENT_SAVE),
                            html.Button('Reintentar proyección', id=_ASSIGNMENT_REPROJECT),
                            html.Div(id=_ASSIGNMENT_RESULT, role='status'),
                        ],
                    ),
                    dcc.Tab(
                        label='Cargos',
                        value='positions',
                        children=[
                            dcc.Store(
                                id=_CATALOG_REVISION,
                                data=_revision(catalog_snapshot),
                            ),
                            html.Label('Seleccionar cargo o crear uno nuevo'),
                            dcc.Dropdown(
                                id=_POSITION_SELECT,
                                options=_position_options(catalog, include_inactive=True),
                                placeholder='Nuevo cargo',
                                clearable=True,
                            ),
                            html.Label('Identificador'),
                            dcc.Input(id=_POSITION_ID, type='text', maxLength=64),
                            html.Label('Nombre del cargo'),
                            dcc.Input(id=_POSITION_LABEL, type='text', maxLength=120),
                            dcc.Checklist(
                                id=_POSITION_ACTIVE,
                                options=[{'label': 'Activo', 'value': 'active'}],
                                value=['active'],
                            ),
                            html.Button('Guardar cargo', id=_CATALOG_SAVE),
                            html.Button('Reintentar proyección', id=_CATALOG_REPROJECT),
                            html.Div(id=_CATALOG_RESULT, role='status'),
                        ],
                    ),
                ],
            ),
        ],
        className='atlanticus-bootstrap',
    )


def register_operational_callbacks(app: object, context: OperationalManagerContext) -> None:
    @app.callback(
        Output(_AREA, 'value'),
        Output(_POSITION, 'value'),
        Output(_GROUP, 'value'),
        Output(_ASSIGNMENT_REVISION, 'data'),
        Input(_USER, 'value'),
    )
    def select_user(user_id):
        if not user_id or not context.can_manage():
            return None, None, None, None
        try:
            snapshot, assignment = context.service.assignment_for_edit(user_id)
            return (
                assignment.area_id,
                assignment.position_id,
                assignment.group_id,
                _revision(snapshot),
            )
        except Exception:
            return None, None, None, None

    @app.callback(
        Output(_POSITION_ID, 'value'),
        Output(_POSITION_LABEL, 'value'),
        Output(_POSITION_ACTIVE, 'value'),
        Output(_POSITION_ID, 'disabled'),
        Input(_POSITION_SELECT, 'value'),
    )
    def select_position(position_id):
        if not context.can_manage():
            return '', '', [], True
        if not position_id:
            return '', '', ['active'], False
        try:
            _, catalog = context.service.catalog_for_edit()
            position = catalog.position(position_id)
            if position is None:
                return '', '', ['active'], False
            return position.id, position.label, ['active'] if position.active else [], True
        except Exception:
            return '', '', [], True

    @app.callback(
        Output(_CATALOG_REVISION, 'data'),
        Output(_POSITION_SELECT, 'options'),
        Output(_POSITION, 'options'),
        Output(_POSITION_SELECT, 'value'),
        Output(_CATALOG_RESULT, 'children'),
        Input(_CATALOG_SAVE, 'n_clicks'),
        State(_POSITION_SELECT, 'value'),
        State(_POSITION_ID, 'value'),
        State(_POSITION_LABEL, 'value'),
        State(_POSITION_ACTIVE, 'value'),
        State(_CATALOG_REVISION, 'data'),
        prevent_initial_call=True,
    )
    def save_position(clicks, selected, position_id, label, active, revision):
        if not clicks or not context.can_manage():
            return no_update, no_update, no_update, no_update, no_update
        try:
            snapshot, catalog = context.service.catalog_for_edit()
            if _revision(snapshot) != revision:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    _message('El catálogo cambió. Recarga la página.'),
                )
            if selected and selected != position_id:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    _message('El identificador del cargo no se puede cambiar.'),
                )
            position = Position(
                id=position_id,
                label=label,
                active='active' in (active or ()),
            )
            updated = tuple(item for item in catalog.positions if item.id != position.id) + (
                position,
            )
            context.service.publish_catalog(
                OperationalCatalog(positions=updated),
                actor=context.principal().subject_id,
                expected=snapshot,
            )
            options = _position_options(OperationalCatalog(positions=updated))
            new_snapshot, _ = context.service.catalog_for_edit()
        except ValueError:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                _message('Los datos del cargo no son válidos.'),
            )
        except Exception:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                _message('No fue posible guardar el cargo. Recarga y reintenta.'),
            )
        try:
            context.service.project_current(CATALOG_SOURCE_KEY)
            result = _message('Cargo guardado y proyectado.')
        except Exception:
            result = _message('Cargo guardado en Source. Usa Reintentar proyección.')
        return (
            _revision(new_snapshot),
            _position_options(OperationalCatalog(positions=updated), include_inactive=True),
            options,
            position.id,
            result,
        )

    @app.callback(
        Output(_ASSIGNMENT_REVISION, 'data', allow_duplicate=True),
        Output(_ASSIGNMENT_RESULT, 'children'),
        Input(_ASSIGNMENT_SAVE, 'n_clicks'),
        State(_USER, 'value'),
        State(_AREA, 'value'),
        State(_POSITION, 'value'),
        State(_GROUP, 'value'),
        State(_ASSIGNMENT_REVISION, 'data'),
        prevent_initial_call=True,
    )
    def save_assignment(clicks, user_id, area, position, group, revision):
        if not clicks or not user_id or not context.can_manage():
            return no_update, no_update
        try:
            snapshot, _ = context.service.assignment_for_edit(user_id)
            if _revision(snapshot) != revision:
                return no_update, _message('La asignación cambió. Selecciona de nuevo al usuario.')
            assignment = OperationalAssignment(
                user_id=user_id,
                area_id=area,
                position_id=position,
                group_id=group,
            )
            context.service.publish_assignment(
                assignment,
                actor=context.principal().subject_id,
                expected=snapshot,
            )
            updated_snapshot, _ = context.service.assignment_for_edit(user_id)
        except Exception:
            return no_update, _message('No fue posible guardar la asignación. Recarga y reintenta.')
        try:
            context.service.project_current(assignment_source_key(user_id))
            result = _message('Asignación guardada y proyectada.')
        except Exception:
            result = _message('Asignación guardada en Source. Usa Reintentar proyección.')
        return _revision(updated_snapshot), result

    @app.callback(
        Output(_CATALOG_RESULT, 'children', allow_duplicate=True),
        Input(_CATALOG_REPROJECT, 'n_clicks'),
        prevent_initial_call=True,
    )
    def reproject_catalog(clicks):
        if not clicks or not context.can_manage():
            return no_update
        try:
            context.service.project_current(CATALOG_SOURCE_KEY)
            return _message('Catálogo proyectado.')
        except Exception:
            return _message('No fue posible proyectar el catálogo.')

    @app.callback(
        Output(_ASSIGNMENT_RESULT, 'children', allow_duplicate=True),
        Input(_ASSIGNMENT_REPROJECT, 'n_clicks'),
        State(_USER, 'value'),
        prevent_initial_call=True,
    )
    def reproject_assignment(clicks, user_id):
        if not clicks or not user_id or not context.can_manage():
            return no_update
        try:
            context.service.project_current(assignment_source_key(user_id))
            return _message('Asignación proyectada.')
        except Exception:
            return _message('No fue posible proyectar la asignación.')


def _revision(snapshot: SourceSnapshot) -> str | None:
    return snapshot.current.release_ref.release_id.value if snapshot.current is not None else None


def _position_options(
    catalog: OperationalCatalog,
    *,
    include_inactive: bool = False,
) -> list[dict[str, object]]:
    return [
        {
            'label': item.label,
            'value': item.id,
            'disabled': not item.active and not include_inactive,
        }
        for item in catalog.positions
    ]


def _message(value: str):
    return html.P(value)
