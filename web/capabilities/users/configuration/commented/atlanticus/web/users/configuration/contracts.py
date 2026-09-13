# Declara los contratos propios de Users Configuration.
# Pending se lee mediante PendingUsersReader de Users core y no se redefine aquí.

from collections.abc import Callable
from typing import Protocol

from atlanticus.web.users.configuration.bundle import UsersConfigurationBundle
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


# La proyección de runtime recibe el snapshot autoritativo completo.
# No expone CRUD por usuario porque las ausencias del snapshot también tienen semántica durable.
class UsersRuntimeProjectionWriter(Protocol):
    def materialize(self, bundle: UsersConfigurationBundle, *, actor: str) -> None: ...

    def health_check(self) -> bool: ...


class UsersProjectionRepository(Protocol):
    def load_state(self) -> UsersProjectionState | None: ...

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState: ...

    def health_check(self) -> bool: ...
