from __future__ import annotations

# Espejo pedagógico del módulo productivo equivalente.
# Navigation separa autorización funcional (public/restricted) de recovery administrativo.
# Los perfiles root/local nunca son grants explícitos; llegan como administrative_override confiable.


from atlanticus.web.navigation.access import can_open_navigation_access
from atlanticus.web.navigation.definition import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)
from atlanticus.web.navigation.models import (
    NavigationDefinition,
    NavigationGroup,
    NavigationGroupDefinition,
    NavigationLinkDefinition,
    NavigationMenu,
    NavigationPrincipal,
)
from atlanticus.web.navigation.principal import (
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationPrincipalProvider,
)
from atlanticus.web.services import ServiceRegistry


def resolve_navigation(
    definition: NavigationDefinition,
    *,
    principal: NavigationPrincipal,
) -> NavigationMenu:
    links = tuple(
        link.to_resolved()
        for link in sorted(definition.links, key=_link_sort_key)
        if link.enabled and _can_open(link, principal)
    )
    groups: list[NavigationGroup] = []
    for group in sorted(definition.groups, key=_group_sort_key):
        if not group.enabled:
            continue
        children = tuple(
            link.to_resolved()
            for link in sorted(group.links, key=_link_sort_key)
            if link.enabled and _can_open(link, principal)
        )
        if children:
            groups.append(group.to_resolved(links=children))
    return NavigationMenu(
        user=principal.user,
        links=links,
        groups=tuple(groups),
    )


def resolve_navigation_from_services(services: ServiceRegistry) -> NavigationMenu:
    definition_provider = services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
        NavigationDefinitionProvider,
    )
    principal_provider = services.require(
        NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
        NavigationPrincipalProvider,
    )
    return resolve_navigation(
        definition_provider.current(),
        principal=principal_provider.current(),
    )


def _can_open(link: NavigationLinkDefinition, principal: NavigationPrincipal) -> bool:
    return can_open_navigation_access(
        access_mode=link.access_mode,
        allowed_profiles=link.allowed_profiles,
        principal=principal,
    )


def _link_sort_key(link: NavigationLinkDefinition) -> tuple[int, str, str]:
    return (link.order, link.label, link.key)


def _group_sort_key(group: NavigationGroupDefinition) -> tuple[int, str, str]:
    return (group.order, group.label, group.key)
