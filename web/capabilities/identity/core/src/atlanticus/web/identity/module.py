from __future__ import annotations

from flask import Flask, request

from atlanticus.web.environment import resolve_environment
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


def create_identity_module(
    provider: IdentityProvider,
    *,
    access_resolver: AccessResolver | None = None,
) -> WebModule:
    resolver = access_resolver or AuthenticatedAccessResolver()

    def register_services(services: ServiceRegistry) -> None:
        if resolve_environment().is_production and not provider.production_ready:
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
            if _is_public_request():
                return None
            try:
                snapshot = _resolve_request_snapshot(bootstrap, runtime)
            except IdentityProviderUnavailableError, AccessResolverUnavailableError:
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


def _is_public_request() -> bool:
    return request.path.startswith(('/assets/', '/health/', '/.auth/'))


def _is_page_document_request() -> bool:
    if request.method != 'GET':
        return False
    if request.path.startswith(('/_dash', '/assets/', '/health/', '/api/', '/.auth/')):
        return False
    best = request.accept_mimetypes.best_match(['text/html', 'application/json'])
    return best == 'text/html'
