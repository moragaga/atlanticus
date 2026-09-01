from collections.abc import Callable
from typing import Protocol

from ada.configuration.kpi_definition.projection import KpiDefinitionProjection
from ada.configuration.kpi_definition.source import KpiDefinitionSourceDocument

KpiDefinitionAuditActorProvider = Callable[[], str]


class KpiDefinitionSource(Protocol):
    def load(self) -> KpiDefinitionSourceDocument | None: ...


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
