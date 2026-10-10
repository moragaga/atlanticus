from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from dash import html, page_registry
from flask import Flask, Request, Response, current_app, g, has_request_context, request

from atlanticus.web.compositions.deployment_access_manager.access import RootManagerAccess
from atlanticus.web.compositions.deployment_access_manager.session import DeploymentRootSession
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

_ROOT_ADMITTED = '_atlanticus_manager_root_admitted'
_DASH_LAYOUT = '/_dash-layout'
_DASH_DEPENDENCIES = '/_dash-dependencies'
_DASH_UPDATE = '/_dash-update-component'
_COMPONENT_SUITE_PREFIX = '/_dash-component-suites/'
_MAX_CALLBACK_REQUEST_BYTES = 2 * 1024 * 1024
_MANAGER_PAGE_EXTENSION = 'atlanticus_root_manager_page_scope'


class RootManagerScopeConfigurationError(ValueError):
    pass


class RootManagerRequestScope:
    def __init__(
        self,
        *,
        root_session: DeploymentRootSession,
        manager_surface: ManagerSurface,
        root_access: RootManagerAccess | None = None,
        operational_access: Callable[[], bool] | None = None,
    ) -> None:
        if not isinstance(root_session, DeploymentRootSession):
            raise RootManagerScopeConfigurationError('Manager ROOT scope requires a ROOT session')
        if not isinstance(manager_surface, ManagerSurface):
            raise RootManagerScopeConfigurationError('Manager ROOT scope requires a ManagerSurface')
        if root_access is not None and (
            not isinstance(root_access, RootManagerAccess)
            or root_access.root_session is not root_session
        ):
            raise RootManagerScopeConfigurationError(
                'Manager ROOT scope requires matching ROOT access'
            )
        if operational_access is not None and not callable(operational_access):
            raise RootManagerScopeConfigurationError('Operational access must be callable')
        prefix = manager_surface.registry.root_route
        if not isinstance(prefix, str) or not prefix.startswith('/') or prefix == '/':
            raise RootManagerScopeConfigurationError(
                'Manager ROOT scope requires a dedicated prefix'
            )
        self._root_access = root_access or RootManagerAccess(root_session=root_session)
        self._operational_access = operational_access
        self._manager_surface = manager_surface
        self._prefix = prefix
        self._manager_routes = frozenset(
            (
                prefix,
                *(
                    manager_surface.registry.route_for(item)
                    for item in manager_surface.registry.items
                ),
            )
        )
        self._pending_outputs: set[str] = set()
        self._allowed_outputs: frozenset[str] = frozenset()
        self._expected_registrations = 0
        self._completed_registrations = 0
        self._ready = False
        self._modules_prepared = False

    def manager_web_modules(self) -> tuple[WebModule, ...]:
        if self._modules_prepared:
            raise RootManagerScopeConfigurationError('Manager ROOT modules are already composed')
        self._modules_prepared = True
        result = []
        for module in self._manager_surface.web_modules:
            register = module.register_callbacks
            if register is None:
                result.append(module)
                continue
            self._expected_registrations += 1
            result.append(replace(module, register_callbacks=self._capture_callbacks(register)))
        return tuple(result)

    def guard_module(self) -> WebModule:
        def register_middlewares(server: Flask, services: ServiceRegistry) -> None:
            if self._operational_access is not None:
                if _MANAGER_PAGE_EXTENSION in server.extensions:
                    raise RootManagerScopeConfigurationError(
                        'Manager ROOT page scope is already registered'
                    )
                server.extensions[_MANAGER_PAGE_EXTENSION] = (self, services)

            @server.before_request
            def reject_unadmitted_manager_requests() -> Response | None:
                admitted = getattr(g, _ROOT_ADMITTED, False)
                path = request.path
                if (path == self._prefix or path.startswith(f'{self._prefix}/')) and (
                    not admitted or request.method != 'GET' or path not in self._manager_routes
                ):
                    return Response('Manager access denied', status=403)
                if path == _DASH_UPDATE and request.method == 'POST' and not admitted:
                    data = request.get_json(silent=True)
                    if (
                        isinstance(data, dict)
                        and isinstance(data.get('output'), str)
                        and data['output'] in self._allowed_outputs
                    ):
                        return Response('Manager access denied', status=403)
                return None

            @server.after_request
            def isolate_root_dependencies(response: Response) -> Response:
                admitted = getattr(g, _ROOT_ADMITTED, False)
                if admitted and (
                    request.path in {_DASH_LAYOUT, _DASH_DEPENDENCIES}
                    or request.path in self._manager_routes
                ):
                    response.headers['Cache-Control'] = 'private, no-store'
                    response.headers['Vary'] = 'Cookie'
                if request.path != _DASH_DEPENDENCIES or response.status_code != 200:
                    return response
                data = response.get_json(silent=True)
                if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                    return Response('Manager callback metadata is unavailable', status=503)
                if admitted and self._operational_ready():
                    filtered = data
                else:
                    filtered = [
                        item
                        for item in data
                        if isinstance(item.get('output'), str)
                        and (item['output'] in self._allowed_outputs) is admitted
                    ]
                response.set_data(json.dumps(filtered, separators=(',', ':')))
                if not admitted:
                    response.headers['Cache-Control'] = 'private, no-store'
                    response.headers['Vary'] = 'Cookie'
                return response

        def register_callbacks(app: Any, services: ServiceRegistry) -> None:
            if (
                not self._modules_prepared
                or self._completed_registrations != self._expected_registrations
            ):
                raise RootManagerScopeConfigurationError(
                    'Manager ROOT callbacks must be registered before the guard'
                )
            if self._ready:
                raise RootManagerScopeConfigurationError('Manager ROOT guard was registered twice')
            original_layout = app.layout
            if not callable(original_layout):
                raise RootManagerScopeConfigurationError('Dash layout must be callable')
            callback_map = getattr(app, 'callback_map', None)
            if not isinstance(callback_map, dict) or not self._pending_outputs.issubset(
                callback_map
            ):
                raise RootManagerScopeConfigurationError(
                    'Manager ROOT callback registration is invalid'
                )
            self._allowed_outputs = frozenset(self._pending_outputs)
            if self._operational_access is not None:
                self._bind_manager_pages(services)

            def scoped_layout() -> object:
                if (
                    has_request_context()
                    and getattr(g, _ROOT_ADMITTED, False)
                    and not self._operational_ready()
                ):
                    return self._manager_surface.layout(services)
                return original_layout()

            app.layout = scoped_layout
            self._ready = True

        return WebModule(
            name='deployment-root-manager-guard',
            register_middlewares=register_middlewares,
            register_callbacks=register_callbacks,
        )

    def authorize(self, incoming: Request) -> bool:
        if not self._ready:
            return False
        path = incoming.path
        method = incoming.method
        manager_page = path in self._manager_routes and method == 'GET'
        dash_read = path in {_DASH_LAYOUT, _DASH_DEPENDENCIES} and method == 'GET'
        dash_asset = path.startswith(_COMPONENT_SUITE_PREFIX) and method == 'GET'
        dash_update = path == _DASH_UPDATE and method == 'POST'
        if not (manager_page or dash_read or dash_asset or dash_update):
            return False
        if dash_update and not self._is_managed_callback(incoming):
            return False
        if self._root_access.current() is None:
            return False
        setattr(g, _ROOT_ADMITTED, True)
        return True

    def _operational_ready(self) -> bool:
        if self._operational_access is None or not has_request_context():
            return False
        try:
            return self._operational_access() is True
        except Exception:
            return False

    def _bind_manager_pages(self, services: ServiceRegistry) -> None:
        registered = {
            page.get('path'): page
            for page in page_registry.values()
            if isinstance(page.get('path'), str)
        }
        missing = self._manager_routes - registered.keys()
        if missing:
            raise RootManagerScopeConfigurationError(
                'Operational Manager navigation requires registered Dash pages: '
                + ', '.join(sorted(missing))
            )

        def manager_page(**_parameters: object) -> object:
            if not has_request_context():
                return html.P('Manager access denied')
            scope_binding = current_app.extensions.get(_MANAGER_PAGE_EXTENSION)
            if not isinstance(scope_binding, tuple) or len(scope_binding) != 2:
                return html.P('Manager access denied')
            scope, scoped_services = scope_binding
            if not isinstance(scope, RootManagerRequestScope) or not isinstance(
                scoped_services, ServiceRegistry
            ):
                return html.P('Manager access denied')
            if scope._root_access.current() is None:
                return html.P('Manager access denied')
            return scope._manager_surface.layout(scoped_services)

        for path in self._manager_routes:
            registered[path]['layout'] = manager_page

    def _capture_callbacks(self, registrar: Callable[..., None]) -> Callable[..., None]:
        def register(app: Any, services: ServiceRegistry) -> None:
            before = set(app.callback_map)
            registrar(app, services)
            added = set(app.callback_map) - before
            self._pending_outputs.update(added)
            self._completed_registrations += 1

        return register

    def _is_managed_callback(self, incoming: Request) -> bool:
        incoming.max_content_length = _MAX_CALLBACK_REQUEST_BYTES
        length = incoming.content_length
        if length is not None and length > _MAX_CALLBACK_REQUEST_BYTES:
            return False
        if incoming.mimetype != 'application/json':
            return False
        data = incoming.get_json(silent=True)
        return (
            isinstance(data, dict)
            and isinstance(data.get('output'), str)
            and data['output'] in self._allowed_outputs
        )
