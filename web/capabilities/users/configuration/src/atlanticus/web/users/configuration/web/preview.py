from __future__ import annotations

from dash import html

from atlanticus.web.users.configuration.models import UsersConfigurationCatalog
from atlanticus.web.users.profiles import has_full_access


def build_users_history_preview(payload: dict[str, object]) -> object:
    catalog = UsersConfigurationCatalog.from_document(payload)
    profiles = catalog.profile_catalog().all()
    enabled_users = sum(user.enabled for user in catalog.users)
    return html.Div(
        [
            _summary(
                (
                    ('Perfiles', str(len(profiles))),
                    ('Perfiles personalizados', str(len(catalog.profiles))),
                    ('Usuarios configurados', str(len(catalog.users))),
                    ('Usuarios habilitados', str(enabled_users)),
                )
            ),
            html.Section(
                [
                    html.H4('Perfiles'),
                    html.Div(
                        [
                            html.Article(
                                [
                                    html.Div(
                                        [html.Strong(profile.label), html.Code(profile.key)],
                                        className='atlanticus-manager__preview-entity-title',
                                    ),
                                    html.Div(
                                        [
                                            _badge(
                                                'Acceso total'
                                                if has_full_access(profile.key)
                                                else 'Acceso restringido'
                                            ),
                                            _badge(f'Fondo {profile.background_color}'),
                                            _badge(f'Texto {profile.text_color}'),
                                        ],
                                        className='atlanticus-manager__preview-badges',
                                    ),
                                ],
                                className='atlanticus-manager__preview-entity',
                            )
                            for profile in profiles
                        ],
                        className='atlanticus-manager__preview-list',
                    ),
                ],
                className='atlanticus-manager__preview-section',
            ),
            html.Section(
                [
                    html.H4('Usuarios'),
                    html.Div(
                        [_user(user) for user in catalog.users]
                        if catalog.users
                        else html.P(
                            'Sin usuarios configurados.',
                            className='atlanticus-manager__preview-empty',
                        ),
                        className='atlanticus-manager__preview-list',
                    ),
                ],
                className='atlanticus-manager__preview-section',
            ),
        ],
        className='atlanticus-manager__preview-content',
    )


def _user(user) -> object:
    identity = (
        f'{user.issuer} · {user.subject_id}'
        if user.issuer is not None and user.subject_id is not None
        else 'Sin identidad Entra vinculada'
    )
    return html.Article(
        [
            html.Div(
                [html.Strong(user.display_name), html.Code(user.user_id)],
                className='atlanticus-manager__preview-entity-title',
            ),
            html.Div(user.email, className='atlanticus-manager__preview-url'),
            html.Small(identity, className='atlanticus-manager__preview-detail'),
            html.Div(
                [
                    _badge(f'Perfil: {user.profile_key}'),
                    _badge('Activo' if user.enabled else 'Deshabilitado'),
                ],
                className='atlanticus-manager__preview-badges',
            ),
        ],
        className='atlanticus-manager__preview-entity',
    )


def _summary(items: tuple[tuple[str, str], ...]) -> object:
    return html.Div(
        [
            html.Div(
                [html.Small(label), html.Strong(value)],
                className='atlanticus-manager__preview-summary-item',
            )
            for label, value in items
        ],
        className='atlanticus-manager__preview-summary',
    )


def _badge(label: str) -> object:
    return html.Span(label, className='atlanticus-manager__preview-badge')
