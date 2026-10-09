# Espejo pedagógico: conserva exactamente el contrato productivo y explica su intención.
from __future__ import annotations

from collections.abc import Callable

from flask import Flask, Request, request

from atlanticus.web.configuration import WebSettings
from atlanticus.web.identity.access import (
    ACCESS_RUNTIME_SERVICE_KEY,
    AccessResolver,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
    AuthenticatedAccessResolver,
)
from atlanticus.web.identity.bootstrap import AccessBootstrap
from atlanticus.web.identity.errors import (
    AccessResolverUnavailableError,
    IdentityConfigurationError,
    IdentityProviderUnavailableError,
)
from atlanticus.web.identity.pages import (
    identity_unavailable_response,
    invalid_identity_response,
    user_disabled_response,
)
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.identity.session import configure_identity_session
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

ACCESS_BOOTSTRAP_SERVICE_KEY = 'atlanticus.web.identity.bootstrap'


# El middleware conserva el contrato normal cuando no existe autorización alternativa.
def create_identity_module(
    provider: IdentityProvider,
    *,
    access_resolver: AccessResolver | None = None,
    independent_routes: tuple[str, ...] = (),
    alternative_request_authorizer: Callable[[Request], bool] | None = None,
) -> WebModule:
    if not isinstance(independent_routes, tuple) or any(
        not isinstance(route, str) for route in independent_routes
    ):
        raise ValueError('Independent route declarations must contain strings')
    if len(independent_routes) != len(set(independent_routes)):
        raise ValueError('Independent route declarations must be unique')
    if any(
        not isinstance(route, str) or not route.startswith('/') or route == '/'
        or route.endswith('/') or '//' in route
        or route.startswith(('/health/', '/assets/', '/.auth/', '/_dash'))
        for route in independent_routes
    ):
        raise ValueError('Independent route declarations contain an invalid route')
    if alternative_request_authorizer is not None and not callable(alternative_request_authorizer):
        raise TypeError('Alternative request authorizer must be callable')
    resolver = access_resolver or AuthenticatedAccessResolver()

    def register_services(services: ServiceRegistry) -> None:
        if WebSettings().environment.is_production and not provider.production_ready:
            raise IdentityConfigurationError(
                f'Identity provider {provider.key!r} is not allowed in production'
            )
        provider.validate_configuration()
        runtime = AccessRuntime()
        services.add(ACCESS_RUNTIME_SERVICE_KEY, runtime)
        services.add(
            ACCESS_BOOTSTRAP_SERVICE_KEY,
            AccessBootstrap(provider=provider, resolver=resolver, runtime=runtime),
        )

    def register_middlewares(server: Flask, services: ServiceRegistry) -> None:
        configure_identity_session(server)
        provider.configure(server)
        bootstrap = services.require(ACCESS_BOOTSTRAP_SERVICE_KEY, AccessBootstrap)
        runtime = services.require(ACCESS_RUNTIME_SERVICE_KEY, AccessRuntime)

        @server.before_request
        def enforce_application_access():
            if _is_public_request(independent_routes):
                return None
            # Un acceso alternativo requiere una decisión explícita y verificable.
            if alternative_request_authorizer is not None:
                try:
                    if alternative_request_authorizer(request) is True:
                        return None
                except Exception:
                    return identity_unavailable_response()
            try:
                snapshot = _resolve_request_snapshot(bootstrap, runtime)
            except (IdentityProviderUnavailableError, AccessResolverUnavailableError):
                return identity_unavailable_response()
            if snapshot.status is AccessStatus.INVALID_IDENTITY:
                return invalid_identity_response()
            if snapshot.status is AccessStatus.USER_DISABLED:
                return user_disabled_response()
            return None

    return WebModule(
        name='identity',
        register_services=register_services,
        register_middlewares=register_middlewares,
    )


# El runtime operacional continúa usando su propia sesión y bootstrap.
def _resolve_request_snapshot(
    bootstrap: AccessBootstrap,
    runtime: AccessRuntime,
) -> AccessSnapshot:
    if _is_page_document_request():
        return bootstrap.refresh(request)
    current = runtime.current_or_none()
    if current is not None:
        return current
    return bootstrap.refresh(request)


def _is_public_request(independent_routes: tuple[str, ...] = ()) -> bool:
    return (request.path in independent_routes
            or request.path.startswith(('/assets/', '/health/', '/.auth/')))


def _is_page_document_request() -> bool:
    if request.method != 'GET':
        return False
    if request.path.startswith(('/_dash', '/assets/', '/health/', '/api/', '/.auth/')):
        return False
    best = request.accept_mimetypes.best_match(['text/html', 'application/json'])
    return best == 'text/html'
