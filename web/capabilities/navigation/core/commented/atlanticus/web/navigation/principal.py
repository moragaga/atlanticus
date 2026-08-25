# Espejo pedagógico: el provider desacopla la obtención del principal de su origen real.
# Una aplicación puede resolverlo manualmente o mediante una composición opcional con Users.
from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.navigation.models import NavigationPrincipal

NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY = 'atlanticus.web.navigation.principal-provider'


class NavigationPrincipalProvider:
    def __init__(self, resolver: Callable[[], NavigationPrincipal]) -> None:
        self._resolver = resolver

    def current(self) -> NavigationPrincipal:
        return self._resolver()
