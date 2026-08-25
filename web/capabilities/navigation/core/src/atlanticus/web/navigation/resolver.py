from __future__ import annotations

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
        if link.enabled and _can_open(link.effective_profiles(None), principal)
    )
    groups: list[NavigationGroup] = []
    for group in sorted(definition.groups, key=_group_sort_key):
        if not group.enabled:
            continue
        children = tuple(
            link.to_resolved()
            for link in sorted(group.links, key=_link_sort_key)
            if link.enabled and _can_open(link.effective_profiles(group), principal)
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


def _can_open(
    allowed_profiles: tuple[str, ...],
    principal: NavigationPrincipal,
) -> bool:
    if principal.unrestricted:
        return True
    return principal.access_key in allowed_profiles


def _link_sort_key(link: NavigationLinkDefinition) -> tuple[int, str, str]:
    return (link.order, link.label, link.key)


def _group_sort_key(group: NavigationGroupDefinition) -> tuple[int, str, str]:
    return (group.order, group.label, group.key)
