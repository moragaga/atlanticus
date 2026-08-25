from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from flask import Flask, Response, request

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.definition import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)
from atlanticus.web.navigation.models import (
    NavigationDefinition,
    NavigationGroupDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
)
from atlanticus.web.navigation.principal import (
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationPrincipalProvider,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.status_pages import StatusPageAction, status_page_response


# Identidad estable de una ruta interna junto con la política que le aplica.
@dataclass(frozen=True, slots=True)
class NavigationRouteMatch:
    key: str
    pathname: str
    enabled: bool
    allowed_profiles: tuple[str, ...]


# Resuelve una URL interna hacia el enlace configurado que representa esa página.
def resolve_navigation_route(
    definition: NavigationDefinition,
    pathname: str,
) -> NavigationRouteMatch | None:
    normalized = normalize_navigation_path(pathname)
    matches: list[NavigationRouteMatch] = []
    for link in definition.links:
        match = _route_match(link, parent=None)
        if match is not None and match.pathname == normalized:
            matches.append(match)
    for group in definition.groups:
        for link in group.links:
            match = _route_match(link, parent=group)
            if match is not None and match.pathname == normalized:
                matches.append(match)
    if len(matches) > 1:
        raise WebDefinitionError(
            f'Navigation definition contains duplicated internal path: {normalized}'
        )
    return matches[0] if matches else None


# Usa la misma política que el menú para decidir si una URL directa puede abrirse.
def can_access_navigation_path(
    definition: NavigationDefinition,
    *,
    principal: NavigationPrincipal,
    pathname: str,
    home_path: str = '/',
) -> bool:
    normalized = normalize_navigation_path(pathname)
    if normalized == normalize_navigation_path(home_path):
        return True
    match = resolve_navigation_route(definition, normalized)
    if match is not None and not match.enabled:
        return False
    if principal.unrestricted:
        return True
    if match is None:
        return False
    return principal.access_key in match.allowed_profiles


# Añade el guard HTTP de Navigation sin acoplarlo a Users ni a una aplicación concreta.
def create_navigation_authorization_module(*, home_path: str = '/') -> WebModule:
    normalized_home = normalize_navigation_path(home_path)

    def register_middlewares(server: Flask, services: ServiceRegistry) -> None:
        definition_provider = services.require(
            NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
            NavigationDefinitionProvider,
        )
        principal_provider = services.require(
            NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
            NavigationPrincipalProvider,
        )

        @server.before_request
        def authorize_navigation_page():
            if not _is_page_document_request():
                return None
            principal = principal_provider.current()
            definition = definition_provider.current()
            if can_access_navigation_path(
                definition,
                principal=principal,
                pathname=request.path,
                home_path=normalized_home,
            ):
                return None
            return access_denied_response(home_path=normalized_home)

    return WebModule(
        name='navigation-authorization',
        register_middlewares=register_middlewares,
    )


# Página Atlanticus que explica el rechazo y ofrece el retorno seguro a la raíz.
def access_denied_response(*, home_path: str = '/') -> Response:
    return status_page_response(
        status_code=403,
        title='Acceso denegado',
        message='No tienes acceso a esta página.',
        action=StatusPageAction(
            label='Volver al inicio',
            href=normalize_navigation_path(home_path),
        ),
    )


# Normaliza rutas para que `/ruta` y `/ruta/` representen la misma página.
def normalize_navigation_path(value: str) -> str:
    raw = value.strip()
    if not raw.startswith('/') or raw.startswith('//'):
        raise WebDefinitionError('Navigation pathname must be an absolute application path')
    path = urlsplit(raw).path or '/'
    if path != '/':
        path = path.rstrip('/') or '/'
    return path


def _route_match(
    link: NavigationLinkDefinition,
    *,
    parent: NavigationGroupDefinition | None,
) -> NavigationRouteMatch | None:
    if link.is_external:
        return None
    enabled = link.enabled and (parent.enabled if parent is not None else True)
    return NavigationRouteMatch(
        key=link.key,
        pathname=normalize_navigation_path(link.href),
        enabled=enabled,
        allowed_profiles=link.effective_profiles(parent),
    )


def _is_page_document_request() -> bool:
    if request.method != 'GET':
        return False
    excluded_prefixes = ('/_dash', '/assets/', '/health/', '/api/', '/.auth/')
    if request.path.startswith(excluded_prefixes):
        return False
    best = request.accept_mimetypes.best_match(['text/html', 'application/json'])
    return best == 'text/html'
