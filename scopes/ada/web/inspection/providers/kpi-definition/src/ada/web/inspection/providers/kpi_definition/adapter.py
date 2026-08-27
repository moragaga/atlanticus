from __future__ import annotations

from ada.configuration.kpi_definition import KpiDefinitionProjectionRepository
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot


class KpiDefinitionProjectionProvider:
    def __init__(self, repository: KpiDefinitionProjectionRepository) -> None:
        self._repository = repository

    def load_snapshot(self) -> KpiDefinitionSnapshot:
        projection = self._repository.load()
        if projection is None:
            return KpiDefinitionSnapshot(definitions=())
        return KpiDefinitionSnapshot(
            definitions=tuple(
                KpiDefinition(kpi_key=definition.kpi_key, fields=definition.fields)
                for definition in projection.configuration.definitions
            )
        )
