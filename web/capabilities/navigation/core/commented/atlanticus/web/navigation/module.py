from __future__ import annotations

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.definition import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)
from atlanticus.web.navigation.models import NavigationDefinition
from atlanticus.web.navigation.principal import (
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationPrincipalProvider,
)
from atlanticus.web.services import ServiceRegistry


# Compone Navigation con una definición fija o con un proveedor dinámico, nunca con ambos.
def create_navigation_module(
    definition: NavigationDefinition | None = None,
    *,
    definition_provider: NavigationDefinitionProvider | None = None,
    principal_provider: NavigationPrincipalProvider | None = None,
) -> WebModule:
    if (definition is None) == (definition_provider is None):
        raise WebDefinitionError(
            'Navigation module requires exactly one definition or definition provider'
        )
    provider = definition_provider or NavigationDefinitionProvider(lambda: definition)

    def register_services(services: ServiceRegistry) -> None:
        services.add(NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY, provider)
        if principal_provider is not None:
            services.add(
                NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
                principal_provider,
            )

    return WebModule(
        name='navigation',
        register_services=register_services,
    )
