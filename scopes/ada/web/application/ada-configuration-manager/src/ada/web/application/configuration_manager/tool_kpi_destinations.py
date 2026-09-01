from __future__ import annotations

from ada.configuration.kpi_configuration import (
    KpiConfigurationValidationError,
    KpiDestination,
    KpiDestinationCatalog,
)
from ada.configuration.tools_lifecycle import ToolConfigurationProjectionRepository

_SYSTEM_DESTINATION_DISPLAY_NAMES = {
    'global_indicators': 'Global Indicators',
    'time_status': 'Time Status',
}


class ToolConfigurationKpiDestinationCatalogProvider:
    def __init__(
        self,
        projection: ToolConfigurationProjectionRepository,
    ) -> None:
        self._projection = projection

    def load(self) -> KpiDestinationCatalog | None:
        projection = self._projection.load()
        if projection is None:
            return None
        structure = projection.configuration.structure
        if structure is None:
            raise KpiConfigurationValidationError(
                'Projected Tool configuration does not contain structure'
            )
        return KpiDestinationCatalog(
            tool_projection_revision=projection.revision,
            destinations=tuple(
                KpiDestination(
                    key=destination_key,
                    display_name=_destination_display_name(
                        structure,
                        destination_key,
                    ),
                )
                for destination_key in structure.kpi_destination_keys
            ),
        )


def _destination_display_name(structure, destination_key: str) -> str:
    system_name = _SYSTEM_DESTINATION_DISPLAY_NAMES.get(destination_key)
    if system_name is not None:
        return system_name
    return structure.component(destination_key).display_name
