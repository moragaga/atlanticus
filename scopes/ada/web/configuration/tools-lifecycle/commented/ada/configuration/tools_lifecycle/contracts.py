# Contratos inyectables del lifecycle; no fijan SharePoint, Cosmos ni otra tecnología.
from collections.abc import Callable
from typing import Protocol

from ada.configuration.tools_lifecycle.projection import ToolConfigurationProjectionSnapshot
from ada.configuration.tools_lifecycle.source import ToolConfigurationSourceSnapshot

ToolConfigurationAuditActorProvider = Callable[[], str]


class ToolConfigurationSource(Protocol):
    def load(self) -> ToolConfigurationSourceSnapshot | None: ...

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ToolConfigurationSourceSnapshot, ...]: ...

    def load_revision(self, revision: str) -> ToolConfigurationSourceSnapshot | None: ...


class ToolConfigurationPublisher(Protocol):
    def publish(
        self,
        document: ToolConfigurationSourceSnapshot,
        *,
        expected_revision: str | None,
    ) -> None: ...


class ToolConfigurationProjectionRepository(Protocol):
    def load(self) -> ToolConfigurationProjectionSnapshot | None: ...

    def save(
        self,
        projection: ToolConfigurationProjectionSnapshot,
    ) -> ToolConfigurationProjectionSnapshot: ...

    def health_check(self) -> bool: ...
