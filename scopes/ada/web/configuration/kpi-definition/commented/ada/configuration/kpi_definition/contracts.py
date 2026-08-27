from typing import Protocol

from ada.configuration.kpi_definition.projection import KpiDefinitionProjection
from ada.configuration.kpi_definition.source import KpiDefinitionSourceDocument


# Puerto de lectura del source; SharePoint será un adapter futuro y no una dependencia del dominio.
class KpiDefinitionSource(Protocol):
    def load(self) -> KpiDefinitionSourceDocument | None: ...


# Puerto de publicación con revisión esperada para permitir concurrencia optimista en adapters reales.
class KpiDefinitionPublisher(Protocol):
    def publish(
        self,
        document: KpiDefinitionSourceDocument,
        *,
        expected_revision: str | None,
    ) -> None: ...


# Puerto durable para la proyección; Cosmos se conectará detrás de esta frontera más adelante.
class KpiDefinitionProjectionRepository(Protocol):
    def load(self) -> KpiDefinitionProjection | None: ...

    def save(self, projection: KpiDefinitionProjection) -> KpiDefinitionProjection: ...

    def health_check(self) -> bool: ...
