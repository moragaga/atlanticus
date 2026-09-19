# Este módulo conecta Navigation con el contrato genérico de Profiles core.
# No define perfiles propios: la composición decide si existe un catálogo y cuál entrega.
from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition

NavigationProfileCatalogProvider = Callable[[], ProfileCatalog]


def profile_definitions(
    provider: NavigationProfileCatalogProvider | None = None,
) -> tuple[ProfileDefinition, ...]:
    if provider is None:
        return ()
    return provider().all()
