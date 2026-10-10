from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from dash import Input, Output, html, page_container
from flask import Request, request

from atlanticus.web.application import create_web_application
from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_INDEPENDENT_ROUTES,
    DeploymentRootSession,
    RootManagerRequestScope,
    compose_root_manager_principal,
    create_deployment_access_manager_entry,
    create_deployment_root_http_module,
)
from atlanticus.web.compositions.deployment_access_manager.session import (
    DeploymentRootSessionError,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessMaterialError,
    DeploymentAccessService,
    LocalDeploymentAccessStorage,
)
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import (
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurface,
    ManagerSurfaceDefinition,
)
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

DEMO_USER = 'demo-root'
DEMO_PASSWORD = 'DemoRoot-Local-Only-2026'
DEMO_MAX_FAILURES = 3
DEMO_LOCK_SECONDS = 30


@dataclass(slots=True)
class _AttemptState:
    failures: int = 0
    blocked_until: float = 0.0


class LocalFailureGate:
    def __init__(
        self,
        *,
        max_failures: int = DEMO_MAX_FAILURES,
        lock_seconds: int = DEMO_LOCK_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_failures < 1 or lock_seconds < 1:
            raise ValueError('Failure gate limits must be positive')
        self._max_failures = max_failures
        self._lock_seconds = lock_seconds
        self._clock = clock or time.monotonic
        self._states: dict[str, _AttemptState] = {}
        self._lock = Lock()

    def allow_login_attempt(self, address: str) -> bool:
        with self._lock:
            state = self._active_state(address)
            return state is None or state.blocked_until == 0.0

    def record_failure(self, address: str) -> None:
        with self._lock:
            state = self._active_state(address)
            if state is None:
                state = _AttemptState()
                self._states[address] = state
            if state.blocked_until:
                return
            state.failures += 1
            if state.failures >= self._max_failures:
                state.blocked_until = self._clock() + self._lock_seconds

    def record_success(self, address: str) -> None:
        with self._lock:
            self._states.pop(address, None)

    def _active_state(self, address: str) -> _AttemptState | None:
        state = self._states.get(address)
        if state is not None and state.blocked_until and self._clock() >= state.blocked_until:
            self._states.pop(address, None)
            return None
        return state


class QualificationRootSession(DeploymentRootSession):
    def __init__(self, *, access: DeploymentAccessService, gate: LocalFailureGate) -> None:
        super().__init__(access=access)
        self._gate = gate

    def login(self, *, service_user: str, password: str):
        address = request.remote_addr or 'unknown'
        try:
            identity = super().login(service_user=service_user, password=password)
        except DeploymentAccessMaterialError, DeploymentRootSessionError:
            self._gate.record_failure(address)
            raise
        self._gate.record_success(address)
        return identity


class QualificationIdentityProvider(IdentityProvider):
    @property
    def key(self) -> str:
        return 'qualification-operational-denied'

    @property
    def production_ready(self) -> bool:
        return False

    def validate_configuration(self) -> None:
        return None

    def resolve(self, _request: Request):
        raise IdentityAuthenticationError('Operational identity is disabled for ROOT qualification')


@dataclass(frozen=True, slots=True)
class QualificationRuntime:
    web: WebApplicationRuntime
    access: DeploymentAccessService
    gate: LocalFailureGate


def build_qualification_runtime(
    *,
    directory: Path,
    gate_clock: Callable[[], float] | None = None,
) -> QualificationRuntime:
    if os.environ.get('ATLANTICUS_ENVIRONMENT', 'local').strip().lower() != 'local':
        raise ValueError('ROOT visual qualification is only available in local environment')
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError('Qualification directory must be an existing absolute directory')

    access = DeploymentAccessService(
        storage=LocalDeploymentAccessStorage(directory / 'qualification-root.zip'),
        application_namespace='atlanticus-root-qualification',
        environment='local',
    )
    access.bootstrap_initial(service_user=DEMO_USER, password=DEMO_PASSWORD)
    gate = LocalFailureGate(clock=gate_clock)
    root_session = QualificationRootSession(access=access, gate=gate)

    def ordinary_principal() -> ManagerPrincipal:
        return ManagerPrincipal(subject_id='qualification-anonymous', display_name='Anonymous')

    principal = compose_root_manager_principal(
        root_session=root_session, fallback=ordinary_principal
    )
    entry = create_deployment_access_manager_entry(
        root_session=root_session,
        principal_provider=principal,
        group_key='administration',
    )
    surface = ManagerSurface(
        ManagerSurfaceDefinition(
            principal_provider=principal,
            groups=(ManagerModuleGroup(key='administration', title='Administración', order=0),),
            modules=(),
            entries=(entry,),
            route_prefix='/manager',
            header_title='Atlanticus ROOT Qualification',
        )
    )
    scope = RootManagerRequestScope(root_session=root_session, manager_surface=surface)

    def register_operational_routes(server, _services: ServiceRegistry) -> None:
        server.add_url_rule(
            '/api/qualification/private',
            endpoint='qualification_private_api',
            view_func=lambda: {'private': True},
            methods=['GET'],
        )

    def register_operational_callbacks(app, _services: ServiceRegistry) -> None:
        @app.callback(
            Output('qualification-private-output', 'children'),
            Input('qualification-private-button', 'n_clicks'),
        )
        def private_callback(_clicks):
            return 'PRIVATE_OPERATIONAL_DATA'

    operational = WebModule(
        name='qualification-operational',
        register_routes=register_operational_routes,
        register_callbacks=register_operational_callbacks,
    )
    web = create_web_application(
        WebApplicationDefinition(
            import_name='qualification',
            metadata=ApplicationMetadata(
                application_id='root-visual-qualification',
                display_name='Atlanticus ROOT Qualification',
                version='0.1.0',
            ),
            publications_root=directory / 'publications',
            layout=lambda _services: html.Div(
                [
                    html.Button('Private', id='qualification-private-button'),
                    html.Div(id='qualification-private-output'),
                    page_container,
                ]
            ),
            page_packages=('qualification.pages',),
            flask_config={'SECRET_KEY': secrets.token_urlsafe(48)},
            modules=(
                create_identity_module(
                    QualificationIdentityProvider(),
                    independent_routes=ROOT_INDEPENDENT_ROUTES,
                    alternative_request_authorizer=scope.authorize,
                ),
                create_deployment_root_http_module(
                    root_session=root_session,
                    allow_login_attempt=gate.allow_login_attempt,
                ),
                operational,
                *scope.manager_web_modules(),
                scope.guard_module(),
            ),
        )
    )
    return QualificationRuntime(web=web, access=access, gate=gate)
