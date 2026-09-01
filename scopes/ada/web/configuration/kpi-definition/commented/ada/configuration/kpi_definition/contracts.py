# Añade el proveedor abstracto de autoridad sin importar la implementación de KPI Configuration.
from collections.abc import Callable
from typing import Protocol

from ada.configuration.kpi_definition.authority import KpiDefinitionAuthorityCatalog
from ada.configuration.kpi_definition.projection import KpiDefinitionProjection
from ada.configuration.kpi_definition.source import KpiDefinitionSourceDocument

KpiDefinitionAuditActorProvider = Callable[[], str]


class KpiDefinitionSource(Protocol):
    def load(self) -> KpiDefinitionSourceDocument | None: ...

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiDefinitionSourceDocument, ...]: ...

    def load_revision(self, revision: str) -> KpiDefinitionSourceDocument | None: ...


class KpiDefinitionPublisher(Protocol):
    def publish(
        self,
        document: KpiDefinitionSourceDocument,
        *,
        expected_revision: str | None,
    ) -> None: ...


class KpiDefinitionProjectionRepository(Protocol):
    def load(self) -> KpiDefinitionProjection | None: ...

    def save(self, projection: KpiDefinitionProjection) -> KpiDefinitionProjection: ...

    def health_check(self) -> bool: ...


class KpiDefinitionAuthorityProvider(Protocol):
    def load(self) -> KpiDefinitionAuthorityCatalog | None: ...
