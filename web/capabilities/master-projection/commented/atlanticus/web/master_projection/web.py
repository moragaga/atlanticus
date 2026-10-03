from __future__ import annotations

# Source Projection conserva su UX; Users agrega confirmación separada para REPLACE.

import hmac
import re
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from flask import Flask, abort, make_response, redirect, render_template_string, request, session

from atlanticus.web.identity.session import configure_identity_session
from atlanticus.web.master_projection.apply import (
    MasterApplyError,
    MasterApplyOutcome,
    MasterProjectionExecutor,
)
from atlanticus.web.master_projection.plan import MasterProjectionPlanner, ProjectionPlanState
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey

MASTER_PROJECTION_ROUTE = '/master-projection'
MASTER_PROJECTION_LOGOUT_ROUTE = '/master-projection/logout'
MASTER_PROJECTION_INDEPENDENT_ROUTES = (
    MASTER_PROJECTION_ROUTE,
    MASTER_PROJECTION_LOGOUT_ROUTE,
)
_SESSION_KEY = '_atlanticus_master_projection_access'
_CSRF_KEY = '_atlanticus_master_projection_csrf'
_PENDING_KEY = '_atlanticus_master_projection_pending'
_RESULT_KEY = '_atlanticus_master_projection_result'
_SESSION_SECONDS = 900
_MAX_LOGIN_BYTES = 4096
_READY = (ProjectionPlanState.NEVER_PROJECTED, ProjectionPlanState.OUTDATED)


class MasterMaterialIdentity(Protocol):
    material_id: str
    service_user: str
    application_namespace: str
    environment: str
    allowed_actions: tuple[str, ...]


class MasterMaterialReader(Protocol):
    def inspect(self) -> str: ...
    def fingerprint(self) -> str | None: ...
    def unlock(
        self,
        *,
        service_user: str,
        password: str,
        application_namespace: str,
        environment: str,
    ) -> MasterMaterialIdentity: ...


class _AbsentMaterialReader:
    def inspect(self) -> str:
        return 'ABSENT'

    def fingerprint(self) -> str | None:
        return None

    def unlock(
        self,
        *,
        service_user: str,
        password: str,
        application_namespace: str,
        environment: str,
    ) -> MasterMaterialIdentity:
        raise RuntimeError('Master Projection material is absent')


_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Master Projection</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1100px;margin:3rem auto;padding:0 1.25rem;line-height:1.5;color:#1b2733}
main{border:1px solid #ccd2d9;border-radius:10px;padding:1.5rem}table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid #dde1e5;padding:.65rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}
label{display:block;margin-top:1rem}input{display:block;padding:.6rem;max-width:100%;width:22rem}
button{margin-top:1rem;padding:.65rem 1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}
.error{color:#8d1b17}a{color:inherit}.notice{border:1px solid #ccd2d9;padding:.8rem;margin:1rem 0}
</style></head><body><main><h1>Master Projection</h1>
{% if status == 'ABSENT' %}
<p role="status">No existe acceso Master Projection configurado actualmente.</p>
{% elif status == 'INVALID' %}
<p role="alert">El material de acceso Master Projection es inválido o no está disponible.</p>
{% elif authenticated %}
{% if can_apply %}
<p role="status">Sesión Master activa. Despliegue manual e individual habilitado.</p>
{% else %}
<p role="status">Sesión Master activa. Vista de planificación exclusivamente de lectura.</p>
{% endif %}
{% if notice %}<p class="notice" role="status">{{ notice }}</p>{% endif %}
{% if planner_error %}<p role="alert">No fue posible consultar el plan de proyecciones.</p>
{% elif plan %}
<h2>Proyecciones</h2><table><thead><tr><th>Source</th><th>Estado</th><th>Dependencias</th><th>Bloqueos</th>
{% if can_apply %}<th>Operación</th>{% endif %}</tr></thead><tbody>
{% for entry in plan.entries %}<tr><td>{{ entry.key.value }}</td><td>{{ entry.state.value }}</td>
<td>{{ entry.prerequisites | map(attribute='value') | join(', ') or '—' }}</td>
<td>{{ entry.blocked_by | map(attribute='value') | join(', ') or '—' }}</td>
{% if can_apply %}<td>
{% if entry.state.value in ('NEVER_PROJECTED', 'OUTDATED') and entry.current_target %}
<form method="post" action="{{ route }}">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input type="hidden" name="intent" value="prepare">
<input type="hidden" name="source_key" value="{{ entry.key.value }}">
<button type="submit">Preparar despliegue</button></form>
{% else %}—{% endif %}
</td>{% endif %}
</tr>{% endfor %}
</tbody></table>

<h2>Users</h2>
<p>Estado: {{ plan.users.state.value }}</p>
{% if plan.users.snapshot_ids %}
<table><thead><tr><th>Snapshot</th>{% if can_apply %}<th>Operación</th>{% endif %}</tr></thead><tbody>
{% for snapshot_id in plan.users.snapshot_ids %}
<tr><td>{{ snapshot_id }}</td>
{% if can_apply %}<td>
{% if plan.users.executable %}
<form method="post" action="{{ route }}">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input type="hidden" name="intent" value="prepare_users">
<input type="hidden" name="snapshot_id" value="{{ snapshot_id }}">
<button type="submit">Preparar reemplazo users-runtime</button></form>
{% else %}—{% endif %}
</td>{% endif %}
</tr>
{% endfor %}
</tbody></table>
{% else %}<p>No hay snapshots Users disponibles.</p>{% endif %}

{% if can_apply and pending %}
<section class="notice"><h2>Confirmar operación</h2>
{% if pending.kind == 'source' %}
<p>Se ejecutará únicamente <strong>{{ pending.source_key }}</strong> desde su Source current.</p>
<p>Target seleccionado:</p><pre>{{ pending.target | tojson(indent=2) }}</pre>
{% elif pending.kind == 'users' %}
<p>Se reemplazará el conjunto completo de <strong>users-runtime</strong> usando el snapshot:</p>
<pre>{{ pending.snapshot_id }}</pre>
<p>Global Users Registry y Tool Membership no serán modificados.</p>
{% endif %}
<form method="post" action="{{ route }}">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input type="hidden" name="intent" value="confirm">
<input type="hidden" name="nonce" value="{{ pending.nonce }}">
<button type="submit">{% if pending.kind == 'source' %}Confirmar despliegue{% else %}Confirmar reemplazo users-runtime{% endif %}</button></form>
<form method="post" action="{{ route }}">
<input type="hidden" name="csrf" value="{{ csrf }}">
<input type="hidden" name="intent" value="cancel">
<button type="submit">Cancelar</button></form>
</section>
{% endif %}
{% else %}<p role="status">El backend de planificación no está configurado para este runtime.</p>{% endif %}
<form method="post" action="{{ logout_route }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<button type="submit">Cerrar sesión Master</button></form>
{% else %}
<p>Acceso independiente de los permisos del Manager. Introduce las credenciales del material Master.</p>
{% if error %}<p class="error" role="alert">Credenciales incorrectas o material no válido.</p>{% endif %}
<form method="post" action="{{ route }}" autocomplete="off">
<input type="hidden" name="csrf" value="{{ csrf }}">
<label for="master-user">Usuario de servicio</label><input id="master-user" name="service_user" maxlength="128" required>
<label for="master-password">Contraseña</label><input id="master-password" type="password" name="password" maxlength="1024" required>
<button type="submit">Acceder</button></form>
{% endif %}
</main></body></html>"""


@dataclass(frozen=True, slots=True)
class MasterProjectionWebBinding:
    application_namespace: str
    environment: str
    planner: MasterProjectionPlanner | None
    reader: MasterMaterialReader | None = None
    executor: MasterProjectionExecutor | None = None

    def __post_init__(self) -> None:
        if not self.application_namespace.strip() or not self.environment.strip():
            raise ValueError('Master Projection application and environment are required')

    def module(self) -> WebModule:
        reader = self.reader or _AbsentMaterialReader()

        def current_status() -> str:
            try:
                status = str(reader.inspect())
            except Exception:
                return 'INVALID'
            return status if status in {'ABSENT', 'PRESENT', 'INVALID'} else 'INVALID'

        def fingerprint() -> str | None:
            try:
                digest = reader.fingerprint()
                return (
                    digest
                    if isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest)
                    else None
                )
            except Exception:
                return None

        def forget() -> None:
            session.pop(_SESSION_KEY, None)
            session.pop(_PENDING_KEY, None)
            session.pop(_RESULT_KEY, None)

        def csrf_token() -> str:
            token = session.get(_CSRF_KEY)
            if not isinstance(token, str) or len(token) != 43:
                token = secrets.token_urlsafe(32)
                session[_CSRF_KEY] = token
            return token

        def require_csrf() -> None:
            supplied = request.form.get('csrf', '')
            expected = session.get(_CSRF_KEY)
            if not isinstance(expected, str) or not hmac.compare_digest(expected, supplied):
                abort(403)

        def authenticated(current_fingerprint: str | None) -> bool:
            authorization = session.get(_SESSION_KEY)
            now = int(time.time())
            if not isinstance(authorization, dict) or not isinstance(current_fingerprint, str):
                forget()
                return False
            issued = authorization.get('issued')
            if (
                type(issued) is not int
                or issued > now
                or now - issued >= _SESSION_SECONDS
                or authorization.get('application') != self.application_namespace
                or authorization.get('environment') != self.environment
                or not isinstance(authorization.get('material_id'), str)
                or not isinstance(authorization.get('actions'), list)
                or 'projection.preview' not in authorization['actions']
                or not hmac.compare_digest(
                    str(authorization.get('fingerprint', '')), current_fingerprint
                )
            ):
                forget()
                return False
            return True

        def authorized_for_apply() -> bool:
            authorization = session.get(_SESSION_KEY)
            return (
                isinstance(authorization, dict)
                and isinstance(authorization.get('actions'), list)
                and 'projection.apply' in authorization['actions']
                and self.executor is not None
                and self.planner is not None
            )

        def pending_valid(plan, pending: object) -> bool:
            if not isinstance(pending, dict) or not isinstance(pending.get('nonce'), str):
                return False
            if pending.get('kind') == 'source':
                if set(pending) != {'kind', 'source_key', 'target', 'nonce'}:
                    return False
                return any(
                    entry.key.value == pending['source_key']
                    and entry.state in _READY
                    and entry.to_dict()['current_target'] == pending['target']
                    for entry in plan.entries
                )
            if pending.get('kind') == 'users':
                if set(pending) != {'kind', 'snapshot_id', 'nonce'}:
                    return False
                return (
                    plan.users.executable
                    and pending['snapshot_id'] in plan.users.snapshot_ids
                )
            return False

        def page(*, error: bool = False, notice: str | None = None, code: int = 200):
            status = current_status()
            if status != 'PRESENT':
                forget()
            current_fingerprint = fingerprint() if status == 'PRESENT' else None
            if status == 'PRESENT' and current_fingerprint is None:
                status = 'INVALID'
                forget()
            authorized = status == 'PRESENT' and authenticated(current_fingerprint)
            can_apply = authorized and authorized_for_apply()
            plan = None
            planner_error = False
            if authorized and self.planner is not None:
                try:
                    plan = self.planner.inspect()
                except Exception:
                    planner_error = True
            pending = session.get(_PENDING_KEY) if can_apply and plan is not None else None
            if pending is not None and not pending_valid(plan, pending):
                session.pop(_PENDING_KEY, None)
                pending = None
                notice = notice or 'La selección cambió. Prepara nuevamente la operación.'
            if authorized and notice is None:
                notice = session.pop(_RESULT_KEY, None)
            rendered = render_template_string(
                _PAGE,
                status=status,
                error=error,
                authenticated=authorized,
                csrf=csrf_token() if status == 'PRESENT' else '',
                plan=plan,
                planner_error=planner_error,
                can_apply=can_apply,
                pending=pending,
                notice=notice,
                route=MASTER_PROJECTION_ROUTE,
                logout_route=MASTER_PROJECTION_LOGOUT_ROUTE,
            )
            result_code = 503 if status == 'INVALID' or (authorized and planner_error) else code
            return make_response(rendered, result_code)

        def execute_action():
            if current_status() != 'PRESENT':
                forget()
                abort(403)
            current_fingerprint = fingerprint()
            if not authenticated(current_fingerprint):
                abort(403)
            require_csrf()
            if not authorized_for_apply():
                abort(403)
            intent = request.form.get('intent', '')
            if intent == 'cancel':
                session.pop(_PENDING_KEY, None)
                return redirect(MASTER_PROJECTION_ROUTE, code=303)

            if intent == 'prepare':
                session.pop(_PENDING_KEY, None)
                selected = request.form.get('source_key', '')
                try:
                    entry = next(
                        (
                            entry
                            for entry in self.planner.inspect().entries
                            if entry.key.value == selected
                        ),
                        None,
                    )
                except Exception:
                    return page(notice='No fue posible consultar el plan.', code=503)
                if entry is None or entry.state not in _READY or entry.current_target is None:
                    return page(notice='La proyección no está disponible para ejecución.', code=409)
                session[_PENDING_KEY] = {
                    'kind': 'source',
                    'source_key': entry.key.value,
                    'target': entry.to_dict()['current_target'],
                    'nonce': secrets.token_urlsafe(24),
                }
                return redirect(MASTER_PROJECTION_ROUTE, code=303)

            if intent == 'prepare_users':
                session.pop(_PENDING_KEY, None)
                selected = request.form.get('snapshot_id', '')
                try:
                    users = self.planner.inspect().users
                except Exception:
                    return page(notice='No fue posible consultar el plan Users.', code=503)
                if not users.executable or selected not in users.snapshot_ids:
                    return page(notice='El snapshot Users no está disponible.', code=409)
                session[_PENDING_KEY] = {
                    'kind': 'users',
                    'snapshot_id': selected,
                    'nonce': secrets.token_urlsafe(24),
                }
                return redirect(MASTER_PROJECTION_ROUTE, code=303)

            if intent != 'confirm':
                abort(400)

            pending = session.pop(_PENDING_KEY, None)
            if (
                not isinstance(pending, dict)
                or not isinstance(pending.get('nonce'), str)
                or not hmac.compare_digest(pending['nonce'], request.form.get('nonce', ''))
            ):
                return page(notice='No existe una selección válida para confirmar.', code=409)
            try:
                plan = self.planner.inspect()
            except Exception:
                return page(notice='No fue posible consultar el plan.', code=503)
            if not pending_valid(plan, pending):
                return page(notice='La selección cambió. Prepara nuevamente la operación.', code=409)

            try:
                if pending['kind'] == 'source':
                    entry = next(
                        entry
                        for entry in plan.entries
                        if entry.key.value == pending['source_key']
                    )
                    result = self.executor.apply(
                        source_key=SourceKey(pending['source_key']),
                        expected_target=entry.current_target,
                    )
                    session[_RESULT_KEY] = (
                        f'Proyección aplicada: {result.source_key.value}.'
                        if result.outcome is MasterApplyOutcome.APPLIED
                        else f'Proyección ya actualizada: {result.source_key.value}.'
                    )
                else:
                    result = self.executor.apply_users(snapshot_id=pending['snapshot_id'])
                    session[_RESULT_KEY] = (
                        f'users-runtime reemplazado desde snapshot {result.snapshot_id}.'
                    )
            except MasterApplyError as error:
                code = (
                    409
                    if error.reason
                    in (
                        'STALE_SELECTION',
                        'SOURCE_MISSING',
                        'BLOCKED',
                        'INVALID_SELECTION',
                    )
                    else 503
                )
                notice = (
                    'La selección cambió o quedó bloqueada. Revisa su estado.'
                    if code == 409
                    else 'No fue posible verificar el despliegue o reemplazo. Consulta el estado antes de reintentar.'
                )
                return page(notice=notice, code=code)
            except Exception:
                return page(
                    notice='No fue posible verificar el despliegue o reemplazo. Consulta el estado antes de reintentar.',
                    code=503,
                )
            return redirect(MASTER_PROJECTION_ROUTE, code=303)

        def dispatch():
            if request.method == 'POST':
                request.max_content_length = _MAX_LOGIN_BYTES
            if request.path == MASTER_PROJECTION_LOGOUT_ROUTE:
                if request.method != 'POST':
                    abort(405)
                if request.content_length is not None and request.content_length > _MAX_LOGIN_BYTES:
                    abort(413)
                require_csrf()
                forget()
                session.pop(_CSRF_KEY, None)
                return redirect(MASTER_PROJECTION_ROUTE, code=303)
            if request.method in ('GET', 'HEAD'):
                return page()
            if request.content_length is not None and request.content_length > _MAX_LOGIN_BYTES:
                abort(413)
            if request.form.get('intent', ''):
                return execute_action()
            if current_status() != 'PRESENT':
                forget()
                return page()
            require_csrf()
            user = request.form.get('service_user', '')
            password = request.form.get('password', '')
            before = fingerprint()
            if before is None:
                forget()
                return page(error=True)
            try:
                identity = reader.unlock(
                    service_user=user,
                    password=password,
                    application_namespace=self.application_namespace,
                    environment=self.environment,
                )
                after = fingerprint()
                if (
                    after is None
                    or not hmac.compare_digest(before, after)
                    or identity.application_namespace != self.application_namespace
                    or identity.environment != self.environment
                    or not isinstance(identity.material_id, str)
                    or not identity.material_id
                    or not isinstance(identity.allowed_actions, tuple)
                    or 'projection.preview' not in identity.allowed_actions
                ):
                    raise ValueError('Master Projection material changed or is unauthorized')
            except Exception:
                forget()
                return page(error=True)
            session[_SESSION_KEY] = {
                'material_id': identity.material_id,
                'fingerprint': after,
                'application': self.application_namespace,
                'environment': self.environment,
                'actions': list(identity.allowed_actions),
                'issued': int(time.time()),
            }
            session.pop(_PENDING_KEY, None)
            session.pop(_RESULT_KEY, None)
            session.pop(_CSRF_KEY, None)
            return redirect(MASTER_PROJECTION_ROUTE, code=303)

        def register_middlewares(server: Flask, _services: ServiceRegistry) -> None:
            configure_identity_session(server)
            current_status()

            @server.before_request
            def serve_independent_master_projection():
                if request.path in MASTER_PROJECTION_INDEPENDENT_ROUTES:
                    return dispatch()
                return None

            @server.after_request
            def protect_master_responses(response):
                if request.path in MASTER_PROJECTION_INDEPENDENT_ROUTES:
                    response.headers['Cache-Control'] = 'no-store, private'
                    response.headers['Pragma'] = 'no-cache'
                    response.headers['X-Content-Type-Options'] = 'nosniff'
                    response.headers['Referrer-Policy'] = 'no-referrer'
                    response.headers['X-Frame-Options'] = 'DENY'
                    response.headers['Content-Security-Policy'] = (
                        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                        "base-uri 'none'; frame-ancestors 'none'"
                    )
                return response

        def register_routes(server: Flask, _services: ServiceRegistry) -> None:
            server.add_url_rule(
                MASTER_PROJECTION_ROUTE,
                'atlanticus_master_projection',
                dispatch,
                methods=['GET', 'POST'],
            )
            server.add_url_rule(
                MASTER_PROJECTION_LOGOUT_ROUTE,
                'atlanticus_master_projection_logout',
                dispatch,
                methods=['POST'],
            )

        return WebModule(
            name='atlanticus-master-projection',
            register_middlewares=register_middlewares,
            register_routes=register_routes,
        )
