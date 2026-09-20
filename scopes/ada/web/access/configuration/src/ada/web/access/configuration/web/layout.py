from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from ada.web.access.configuration.editor import build_initial_configuration
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.web.ids import (
    ACCESS_KEY_INPUT_ID,
    ACCESS_LIST_ID,
    ADD_ACCESS_ID,
    ADD_ACCESS_RESULT_ID,
    APPLY_ASSIGNMENTS_ID,
    ASSIGNMENTS_RESULT_ID,
    CONFIGURATION_STORE_ID,
    MOUNT_STORE_ID,
    PROFILE_ASSIGNMENTS_ID,
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_NAME_ID,
    access_remove_id,
    profile_access_id,
)
from ada.web.access.configuration.web.models import AdaAccessAdminWebContext
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


def build_ada_access_admin_configuration(context: AdaAccessAdminWebContext) -> object:
    configuration = build_initial_configuration()
    profiles = context.profile_catalog_provider()
    return html.Div(
        [
            dcc.Store(
                id=CONFIGURATION_STORE_ID,
                data=configuration.to_document(),
                storage_type='memory',
            ),
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            _access_catalog_section(configuration),
            _profile_assignments_section(configuration, profiles),
            _save_section(),
        ],
        className='ada-access-admin atlanticus-bootstrap',
    )


def render_access_catalog(configuration: AdaAccessConfiguration) -> object:
    if not configuration.access_keys:
        return html.P(
            'No hay accesos definidos.',
            className='ada-access-admin__empty',
        )
    return [
        html.Article(
            [
                html.Code(access_key),
                dbc.Button(
                    'Eliminar',
                    id=access_remove_id(access_key),
                    n_clicks=0,
                    color='secondary',
                    outline=True,
                    size='sm',
                ),
            ],
            className='ada-access-admin__access-row',
        )
        for access_key in configuration.access_keys
    ]


def render_profile_assignments(
    configuration: AdaAccessConfiguration,
    profiles: ProfileCatalog | None,
) -> object:
    if profiles is None:
        return html.P(
            'La proyección de Profiles no está disponible.',
            className='ada-access-admin__empty',
        )
    return [_profile_assignment_row(configuration, profile) for profile in profiles.all()]


def _runtime_context(context: AdaAccessAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ],
                className='ada-access-admin__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ],
                className='ada-access-admin__runtime-source',
            ),
        ],
        className='ada-access-admin__runtime-context',
    )


def _access_catalog_section(configuration: AdaAccessConfiguration) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Accesos definidos'),
                            html.P(
                                'Cada clave es un identificador estable que el desarrollador '
                                'puede consumir explícitamente.'
                            ),
                        ],
                        className='ada-access-admin__section-copy',
                    ),
                    html.Div(
                        [
                            dbc.Input(
                                id=ACCESS_KEY_INPUT_ID,
                                type='text',
                                placeholder='alarms.view',
                            ),
                            dbc.Button(
                                '+ Acceso',
                                id=ADD_ACCESS_ID,
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                            ),
                        ],
                        className='ada-access-admin__access-create',
                    ),
                ],
                className='ada-access-admin__section-heading',
            ),
            html.Div(id=ADD_ACCESS_RESULT_ID),
            html.Div(
                render_access_catalog(configuration),
                id=ACCESS_LIST_ID,
                className='ada-access-admin__access-list',
            ),
        ],
        className='ada-access-admin__section',
    )


def _profile_assignments_section(
    configuration: AdaAccessConfiguration,
    profiles: ProfileCatalog | None,
) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Asignación por Profiles'),
                            html.P(
                                'Los Profiles provienen de la proyección vigente de Profiles. '
                                'Cada Profile puede recibir cero o más accesos definidos.'
                            ),
                        ],
                        className='ada-access-admin__section-copy',
                    ),
                    dbc.Button(
                        'Aplicar asignaciones',
                        id=APPLY_ASSIGNMENTS_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        disabled=profiles is None,
                    ),
                ],
                className='ada-access-admin__section-heading',
            ),
            html.Div(id=ASSIGNMENTS_RESULT_ID),
            html.Div(
                render_profile_assignments(configuration, profiles),
                id=PROFILE_ASSIGNMENTS_ID,
                className='ada-access-admin__profile-list',
            ),
        ],
        className='ada-access-admin__section',
    )


def _profile_assignment_row(
    configuration: AdaAccessConfiguration,
    profile: ProfileDefinition,
) -> object:
    grant = next(
        (item for item in configuration.profile_access if item.profile_key == profile.key),
        None,
    )
    selected = [] if grant is None else list(grant.access_keys)
    return html.Article(
        [
            html.Div(
                [
                    html.Span(
                        profile.label,
                        className='ada-access-admin__profile-badge',
                        style={
                            'backgroundColor': profile.background_color,
                            'color': profile.text_color,
                        },
                    ),
                    html.Code(profile.key),
                ],
                className='ada-access-admin__profile-copy',
            ),
            dcc.Dropdown(
                id=profile_access_id(profile.key),
                options=[
                    {'label': access_key, 'value': access_key}
                    for access_key in configuration.access_keys
                ],
                value=selected,
                multi=True,
                searchable=True,
                placeholder='Sin accesos',
                className='ada-access-admin__profile-select',
            ),
        ],
        className='ada-access-admin__profile-row',
    )


def _save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · accesos'),
                            html.P(
                                'Guarda las definiciones y asignaciones en el workspace '
                                'de este navegador.'
                            ),
                        ],
                        className='ada-access-admin__section-copy',
                    ),
                    dbc.Button(
                        'Guardar borrador',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        color='primary',
                    ),
                ],
                className='ada-access-admin__section-heading',
            ),
            html.Div(id=SAVE_RESULT_ID),
        ],
        className='ada-access-admin__section ada-access-admin__section--footer',
    )
