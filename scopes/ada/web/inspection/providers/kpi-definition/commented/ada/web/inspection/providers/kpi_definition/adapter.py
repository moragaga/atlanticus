from __future__ import annotations

from ada.configuration.kpi_definition import KpiDefinitionProjectionRepository
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot


# Este adapter es la única frontera entre la proyección descriptiva y el contrato reusable
# de Inspection. No conoce Cosmos ni el lifecycle de warmup/refresh.
class KpiDefinitionProjectionProvider:
    def __init__(self, repository: KpiDefinitionProjectionRepository) -> None:
        # El repositorio se inyecta para que la topología física permanezca fuera del adapter.
        self._repository = repository

    def load_snapshot(self) -> KpiDefinitionSnapshot:
        # Cada carga corresponde a una decisión explícita del lifecycle, nunca a un click.
        projection = self._repository.load()
        if projection is None:
            # La ausencia de proyección equivale a un catálogo descriptivo vacío y válido.
            return KpiDefinitionSnapshot(definitions=())
        # Se traduce el dominio de configuración al contrato propio de Inspection sin
        # compartir instancias ni introducir campos sintéticos.
        return KpiDefinitionSnapshot(
            definitions=tuple(
                KpiDefinition(kpi_key=definition.kpi_key, fields=definition.fields)
                for definition in projection.configuration.definitions
            )
        )
