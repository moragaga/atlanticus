from __future__ import annotations

from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationDefinitionProvider,
    NavigationPrincipalProvider,
    create_navigation_module,
)
from atlanticus.web.navigation.configuration.contracts import NavigationProjectionRepository


# Convierte una proyección activa en un proveedor dinámico de la definición de Navigation.
def create_projected_navigation_definition_provider(
    projection: NavigationProjectionRepository,
) -> NavigationDefinitionProvider:
    def resolve() -> NavigationDefinition:
        current = projection.load()
        if current is None:
            return NavigationDefinition()
        return current.definition

    return NavigationDefinitionProvider(resolve)


# Alternativa de composición al módulo manual: Navigation obtiene su definición desde Projection.
def create_projected_navigation_module(
    projection: NavigationProjectionRepository,
    *,
    principal_provider: NavigationPrincipalProvider | None = None,
) -> WebModule:
    return create_navigation_module(
        definition_provider=create_projected_navigation_definition_provider(projection),
        principal_provider=principal_provider,
    )
