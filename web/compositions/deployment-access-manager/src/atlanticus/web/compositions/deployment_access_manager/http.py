from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from html import escape

from flask import Flask, Response, redirect, request, session

from atlanticus.web.compositions.deployment_access_manager.session import (
    DeploymentRootSession,
    DeploymentRootSessionError,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessMaterialError,
    DeploymentAccessStorageError,
)
from atlanticus.web.identity.session import configure_identity_session
from atlanticus.web.modules import WebModule

ROOT_LOGIN_PATH = '/manager-root/login'
ROOT_STATUS_PATH = '/manager-root/status'
ROOT_LOGOUT_PATH = '/manager-root/logout'
ROOT_INDEPENDENT_ROUTES = (ROOT_LOGIN_PATH, ROOT_STATUS_PATH, ROOT_LOGOUT_PATH)
_CSRF_KEY = '_atlanticus_deployment_root_http_csrf_v1'
_FORM_LIMIT = 8192


class DeploymentRootHttpConfigurationError(ValueError):
    pass


def create_deployment_root_http_module(
    *,
    root_session: DeploymentRootSession,
    allow_login_attempt: Callable[[str], bool],
) -> WebModule:
    if not isinstance(root_session, DeploymentRootSession):
        raise DeploymentRootHttpConfigurationError('ROOT HTTP requires DeploymentRootSession')
    if not callable(allow_login_attempt):
        raise DeploymentRootHttpConfigurationError('ROOT HTTP requires a login attempt gate')

    def register_middlewares(server: Flask, _services: object) -> None:
        configure_identity_session(server)

        @server.before_request
        def bound_root_request_size() -> None:
            if request.path in (ROOT_LOGIN_PATH, ROOT_LOGOUT_PATH) and request.method == 'POST':
                request.max_content_length = _FORM_LIMIT

        @server.after_request
        def secure_root_responses(response: Response) -> Response:
            if request.path in ROOT_INDEPENDENT_ROUTES:
                response.headers['Cache-Control'] = 'no-store, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Referrer-Policy'] = 'no-referrer'
                response.headers['X-Content-Type-Options'] = 'nosniff'
                response.headers['X-Frame-Options'] = 'DENY'
                response.headers['Content-Security-Policy'] = (
                    "default-src 'none'; form-action 'self'; base-uri 'none'; "
                    "frame-ancestors 'none'"
                )
            return response

    def register_routes(server: Flask, _services: object) -> None:
        def login() -> Response:
            if request.method == 'GET':
                return _page('Acceso ROOT', _login_form(_issue_csrf()))
            if request.mimetype != 'application/x-www-form-urlencoded':
                return _page('Solicitud inválida', 'Solicitud inválida.', status=415)
            if not _valid_csrf():
                return _page('Solicitud inválida', 'Solicitud inválida.', status=400)
            if (
                len(request.form.getlist('service_user')) != 1
                or len(request.form.getlist('password')) != 1
            ):
                return _page('Solicitud inválida', 'Solicitud inválida.', status=400)
            service_user = request.form['service_user']
            password = request.form['password']
            if (
                not isinstance(service_user, str)
                or not 0 < len(service_user) <= 128
                or not isinstance(password, str)
                or not 0 < len(password) <= 1024
            ):
                return _page('Solicitud inválida', 'Solicitud inválida.', status=400)
            try:
                permitted = allow_login_attempt(request.remote_addr or 'unknown')
            except Exception:
                return _page('Servicio no disponible', 'Acceso no disponible.', status=503)
            if permitted is not True:
                return _page('Acceso temporalmente limitado', 'Intenta más tarde.', status=429)
            try:
                root_session.login(service_user=service_user, password=password)
            except DeploymentAccessMaterialError, DeploymentRootSessionError:
                return _page('Acceso denegado', 'Credenciales ROOT inválidas.', status=401)
            except DeploymentAccessStorageError:
                return _page('Servicio no disponible', 'Acceso no disponible.', status=503)
            session.pop(_CSRF_KEY, None)
            return redirect(ROOT_STATUS_PATH, code=303)

        def status() -> Response:
            try:
                identity = root_session.current()
            except DeploymentAccessStorageError, DeploymentRootSessionError:
                return _page('Servicio no disponible', 'Acceso no disponible.', status=503)
            if identity is None:
                return _page('Sin sesión ROOT', 'La sesión ROOT no está activa.', status=401)
            return _page('Sesión ROOT activa', _logout_form(_issue_csrf()))

        def logout() -> Response:
            if not _valid_csrf():
                return _page('Solicitud inválida', 'Solicitud inválida.', status=400)
            root_session.logout()
            session.pop(_CSRF_KEY, None)
            return redirect(ROOT_LOGIN_PATH, code=303)

        server.add_url_rule(
            ROOT_LOGIN_PATH,
            endpoint='atlanticus_deployment_root_login',
            view_func=login,
            methods=['GET', 'POST'],
        )
        server.add_url_rule(
            ROOT_STATUS_PATH,
            endpoint='atlanticus_deployment_root_status',
            view_func=status,
            methods=['GET'],
        )
        server.add_url_rule(
            ROOT_LOGOUT_PATH,
            endpoint='atlanticus_deployment_root_logout',
            view_func=logout,
            methods=['POST'],
        )

    return WebModule(
        name='deployment-root-http',
        register_middlewares=register_middlewares,
        register_routes=register_routes,
    )


def _issue_csrf() -> str:
    token = session.get(_CSRF_KEY)
    if not isinstance(token, str) or not token or len(token) > 64:
        token = secrets.token_urlsafe(32)
        session[_CSRF_KEY] = token
    return token


def _valid_csrf() -> bool:
    expected = session.get(_CSRF_KEY)
    presented = request.form.getlist('csrf_token')
    return (
        isinstance(expected, str)
        and bool(expected)
        and len(expected) <= 64
        and len(presented) == 1
        and isinstance(presented[0], str)
        and hmac.compare_digest(expected, presented[0])
    )


def _login_form(token: str) -> str:
    return (
        '<form method="post" action="/manager-root/login">'
        '<label>Usuario ROOT<input name="service_user" autocomplete="username" required></label>'
        '<label>Contraseña<input name="password" type="password" '
        'autocomplete="current-password" required></label>'
        f'<input type="hidden" name="csrf_token" value="{escape(token, quote=True)}">'
        '<button type="submit">Ingresar</button></form>'
    )


def _logout_form(token: str) -> str:
    return (
        '<p>La sesión ROOT fue autenticada. El acceso al Manager depende de que el host '
        'componga la superficie administrativa y la protección de acceso.</p>'
        '<form method="post" action="/manager-root/logout">'
        f'<input type="hidden" name="csrf_token" value="{escape(token, quote=True)}">'
        '<button type="submit">Cerrar sesión ROOT</button></form>'
    )


def _page(title: str, body: str, *, status: int = 200) -> Response:
    return Response(
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        f'<title>{escape(title)}</title></head><body><main>'
        f'<h1>{escape(title)}</h1>{body}'
        '</main></body></html>',
        status=status,
        content_type='text/html; charset=utf-8',
    )
