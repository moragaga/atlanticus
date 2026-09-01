# Define dependencias abstractas para que KPI Definition no conozca adaptadores físicos.
from collections.abc import Callable
from typing import Protocol

from ada.configuration.kpi_definition.projection import KpiDefinitionProjection
from ada.configuration.kpi_definition.source import KpiDefinitionSourceDocument

# El actor se resuelve desde la composition root y no desde identidad global.
KpiDefinitionAuditActorProvider = Callable[[], str]


# Contrato mínimo de lectura de la fuente autoritativa.
class KpiDefinitionSource(Protocol):
    def load(self) -> KpiDefinitionSourceDocument | None: ...

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiDefinitionSourceDocument, ...]: ...

    def load_revision(self, revision: str) -> KpiDefinitionSourceDocument | None: ...


# Contrato mínimo de publicación con optimistic concurrency.
class KpiDefinitionPublisher(Protocol):
    def publish(
        self,
        document: KpiDefinitionSourceDocument,
        *,
        expected_revision: str | None,
    ) -> None: ...


# Contrato de la proyección activa, independiente de Cosmos u otra tecnología.
class KpiDefinitionProjectionRepository(Protocol):
    def load(self) -> KpiDefinitionProjection | None: ...

    def save(self, projection: KpiDefinitionProjection) -> KpiDefinitionProjection: ...

    def health_check(self) -> bool: ...
