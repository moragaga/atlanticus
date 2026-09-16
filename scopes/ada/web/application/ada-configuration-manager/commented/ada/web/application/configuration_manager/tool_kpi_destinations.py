# Espejo pedagógico: deriva destinos KPI desde la proyección activa de Tools conservando el ProjectionTarget completo.
from __future__ import annotations

from ada.web.kpis.configuration import (
    KpiConfigurationValidationError,
    KpiDestination,
    KpiDestinationCatalog,
    KpiDestinationCatalogSnapshot,
)
from ada.web.tools.configuration import ToolConfiguration
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey

_SYSTEM_DESTINATION_DISPLAY_NAMES = {
    'global_indicators': 'Global Indicators',
    'time_status': 'Time Status',
}


# KPI Configuration consume la proyección activa de Tools y conserva su ProjectionTarget como dependencia exacta.
class ToolConfigurationKpiDestinationCatalogProvider:
    def __init__(
        self,
        *,
        projection: ProjectionStore[ToolConfiguration],
        source_key: SourceKey,
    ) -> None:
        self._projection = projection
        self._source_key = source_key

    # Los subcomponentes siguen siendo semántica de Alarmas; sólo kpi_destination_keys forman este catálogo.
    def load(self) -> KpiDestinationCatalogSnapshot | None:
        projection = self._projection.get_active(self._source_key)
        if projection is None:
            return None
        if not isinstance(projection.payload, ToolConfiguration):
            raise KpiConfigurationValidationError('Projected Tool configuration payload is invalid')
        structure = projection.payload.structure
        if structure is None:
            raise KpiConfigurationValidationError(
                'Projected Tool configuration does not contain structure'
            )
        catalog = KpiDestinationCatalog(
            destinations=tuple(
                KpiDestination(
                    key=destination_key,
                    display_name=_destination_display_name(structure, destination_key),
                )
                for destination_key in structure.kpi_destination_keys
            ),
        )
        return KpiDestinationCatalogSnapshot(
            projection_target=projection.target,
            catalog=catalog,
        )


def _destination_display_name(structure, destination_key: str) -> str:
    system_name = _SYSTEM_DESTINATION_DISPLAY_NAMES.get(destination_key)
    if system_name is not None:
        return system_name
    return structure.component(destination_key).display_name
