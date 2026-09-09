from __future__ import annotations

from ada.web.kpis.configuration import KpiConfigurationProjectionRepository
from ada.web.kpis.definition import KpiDefinitionAuthorityCatalog


class KpiConfigurationDefinitionAuthorityProvider:
    def __init__(
        self,
        projection: KpiConfigurationProjectionRepository,
    ) -> None:
        self._projection = projection

    def load(self) -> KpiDefinitionAuthorityCatalog | None:
        projection = self._projection.load()
        if projection is None:
            return None
        catalog = projection.catalog()
        return KpiDefinitionAuthorityCatalog(
            kpi_configuration_revision=catalog.revision,
            kpi_keys=catalog.kpi_keys,
        )
