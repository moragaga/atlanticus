# Compone el Collector operacional sin mover Tool/Cosmos al core de Generic Application.
# El caller debe resolver externamente el ProjectionRecord CURRENT y el cliente Cosmos.

from __future__ import annotations

from ada.web.kpis.collector import (
    AdaKpiCollector,
    CosmosKpiDeliveryReader,
    KpiCollectorPollingSettings,
    KpiCollectorPresentationSettings,
    attach_ada_kpi_collector,
)
from ada.web.tools.configuration import (
    ToolConfiguration,
    validate_ada_operational_tool_configuration,
)
from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.projection.models import ProjectionRecord


def attach_operational_kpi_collector(
    definition: WebApplicationDefinition,
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
    cosmos_client: object,
    polling_settings: KpiCollectorPollingSettings | None = None,
    presentation_settings: KpiCollectorPresentationSettings | None = None,
) -> WebApplicationDefinition:
    # Exige los contratos reales de composición y evita reconstruir identidad desde configuración.
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be WebApplicationDefinition')
    if not isinstance(tool_projection, ProjectionRecord):
        raise TypeError('tool_projection must be a ProjectionRecord')
    configuration = tool_projection.payload
    if not isinstance(configuration, ToolConfiguration):
        raise TypeError('tool_projection payload must be ToolConfiguration')

    # Sólo una Tool operacional completa puede originar los Component Stores del Collector.
    validate_ada_operational_tool_configuration(configuration)
    structure = configuration.structure
    if structure is None:
        raise ValueError('Operational Tool projection requires Tool Structure')

    # La compatibilidad del delivery usa exactamente el SourceReleaseId de la Tool Projection.
    collector = AdaKpiCollector(
        structure=structure,
        tool_projection_revision=tool_projection.source_release_id.value,
        reader=CosmosKpiDeliveryReader(client=cosmos_client),
    )

    # El attachment existente conserva lifecycle, polling, observability y browser stores.
    return attach_ada_kpi_collector(
        definition,
        collector,
        polling_settings=polling_settings,
        presentation_settings=presentation_settings,
    )
