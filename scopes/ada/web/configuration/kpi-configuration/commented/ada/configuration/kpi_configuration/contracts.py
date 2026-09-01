# Declara los contratos abstractos sin infraestructura física.
from collections.abc import Callable
from typing import Protocol

from ada.configuration.kpi_configuration.destinations import KpiDestinationCatalog
from ada.configuration.kpi_configuration.projection import KpiConfigurationProjection
from ada.configuration.kpi_configuration.source import KpiConfigurationSourceDocument

KpiConfigurationAuditActorProvider = Callable[[], str]


class KpiConfigurationSource(Protocol):
    def load(self) -> KpiConfigurationSourceDocument | None: ...

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiConfigurationSourceDocument, ...]: ...

    def load_revision(
        self,
        revision: str,
    ) -> KpiConfigurationSourceDocument | None: ...


class KpiConfigurationPublisher(Protocol):
    def publish(
        self,
        document: KpiConfigurationSourceDocument,
        *,
        expected_revision: str | None,
    ) -> None: ...


class KpiConfigurationProjectionRepository(Protocol):
    def load(self) -> KpiConfigurationProjection | None: ...

    def save(
        self,
        projection: KpiConfigurationProjection,
    ) -> KpiConfigurationProjection: ...

    def health_check(self) -> bool: ...


class KpiDestinationCatalogProvider(Protocol):
    def load(self) -> KpiDestinationCatalog | None: ...
