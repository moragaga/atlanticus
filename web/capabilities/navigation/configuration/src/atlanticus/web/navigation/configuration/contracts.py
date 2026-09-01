from collections.abc import Callable
from typing import Protocol

from atlanticus.web.navigation.configuration.bundle import NavigationConfigurationBundle
from atlanticus.web.navigation.configuration.projection import NavigationConfigurationProjection

NavigationAuditActorProvider = Callable[[], str]


class NavigationConfigurationSource(Protocol):
    def fetch_bundle(self) -> NavigationConfigurationBundle | None: ...

    def list_history(self, *, limit: int = 20) -> tuple[NavigationConfigurationBundle, ...]: ...

    def fetch_revision(self, revision: str) -> NavigationConfigurationBundle | None: ...


class NavigationConfigurationPublisher(Protocol):
    def publish_bundle(
        self,
        bundle: NavigationConfigurationBundle,
        *,
        expected_source_revision: str | None,
    ) -> None: ...


class NavigationProjectionRepository(Protocol):
    def load(self) -> NavigationConfigurationProjection | None: ...

    def save(
        self,
        projection: NavigationConfigurationProjection,
    ) -> NavigationConfigurationProjection: ...

    def health_check(self) -> bool: ...
