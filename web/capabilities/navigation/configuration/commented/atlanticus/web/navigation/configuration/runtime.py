from __future__ import annotations

from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationDefinitionProvider,
    NavigationPrincipalProvider,
    create_navigation_module,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.projection.errors import ProjectionInvariantError
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


# Convierte el ProjectionRecord canónico activo de una SourceKey en la definición dinámica de Navigation.
def create_projected_navigation_definition_provider(
    projection: ProjectionStore[NavigationConfigurationCatalog],
    *,
    source_key: SourceKey,
) -> NavigationDefinitionProvider:
    def resolve() -> NavigationDefinition:
        # El runtime consulta exclusivamente la proyección activa de la SourceKey configurada.
        current = projection.get_active(source_key)
        if current is None:
            return NavigationDefinition()
        # Un store que responde otra SourceKey rompe el contrato canónico y no debe renderizarse.
        if current.source_key != source_key:
            raise ProjectionInvariantError('Projection store returned a different source key')
        # El payload proyectado pertenece al dominio Navigation y produce la definición consumible.
        return current.payload.to_definition()

    return NavigationDefinitionProvider(resolve)


# Compone Navigation con ProjectionStore canónico sin conocer repositories ni revisiones legacy.
def create_projected_navigation_module(
    projection: ProjectionStore[NavigationConfigurationCatalog],
    *,
    source_key: SourceKey,
    principal_provider: NavigationPrincipalProvider | None = None,
) -> WebModule:
    return create_navigation_module(
        definition_provider=create_projected_navigation_definition_provider(
            projection,
            source_key=source_key,
        ),
        principal_provider=principal_provider,
    )
