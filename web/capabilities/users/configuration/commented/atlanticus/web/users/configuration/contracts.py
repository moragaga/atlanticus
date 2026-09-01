# Declara los contratos de Users; la publicación incluye expected_source_revision como precondición explícita.
# El contrato conserva la independencia respecto del backend concreto.

from collections.abc import Callable
from typing import Protocol

from atlanticus.web.users.configuration.bundle import UsersConfigurationBundle
from atlanticus.web.users.configuration.models import DiscoveredUser
from atlanticus.web.users.configuration.projection import UsersProjectionState

UsersAuditActorProvider = Callable[[], str]


class UsersConfigurationSource(Protocol):
    def fetch_bundle(self) -> UsersConfigurationBundle | None: ...

    def list_history(self, *, limit: int = 20) -> tuple[UsersConfigurationBundle, ...]: ...

    def fetch_revision(self, revision: str) -> UsersConfigurationBundle | None: ...


class UsersConfigurationPublisher(Protocol):
    def publish_bundle(
        self,
        bundle: UsersConfigurationBundle,
        *,
        expected_source_revision: str | None,
    ) -> None: ...


class UsersProjectionRepository(Protocol):
    def load_state(self) -> UsersProjectionState | None: ...

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState: ...

    def health_check(self) -> bool: ...


class DiscoveredUsersSource(Protocol):
    def list_discovered(self) -> tuple[DiscoveredUser, ...]: ...
