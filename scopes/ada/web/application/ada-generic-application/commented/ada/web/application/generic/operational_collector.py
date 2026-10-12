from __future__ import annotations

from collections.abc import Callable

from ada.contracts.tools.structure import ToolStructure
from ada.web.alarms.collector import (
    AdaAlarmCollector,
    AlarmCollectorPollingSettings,
    AlarmCollectorPresentationSettings,
    AlarmLiveReaderSettings,
    CosmosAlarmLiveReader,
    attach_ada_alarm_collector,
    attach_ada_alarm_presentation_store,
)
from ada.web.kpis.collector import (
    AdaKpiCollector,
    CosmosKpiDeliveryReader,
    CosmosKpiDeliveryReaderSettings,
    KpiCollectorPollingSettings,
    KpiCollectorPresentationSettings,
    attach_ada_kpi_collector,
    attach_ada_kpi_presentation_stores,
)
from ada.web.tools.configuration import (
    ToolConfiguration,
    validate_ada_operational_tool_configuration,
)
from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.projection.models import ProjectionRecord


# El Collector se deriva de la Projection READY exacta y queda ligado a su source_release_id.
def create_operational_kpi_collector(
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
    cosmos_client: object,
    reader_settings: CosmosKpiDeliveryReaderSettings | None = None,
) -> AdaKpiCollector:
    structure = _resolve_operational_structure(tool_projection)
    resolved_reader_settings = reader_settings or CosmosKpiDeliveryReaderSettings()
    if not isinstance(resolved_reader_settings, CosmosKpiDeliveryReaderSettings):
        raise TypeError('reader_settings must be CosmosKpiDeliveryReaderSettings')
    return AdaKpiCollector(
        structure=structure,
        tool_projection_revision=tool_projection.source_release_id.value,
        reader=CosmosKpiDeliveryReader(
            client=cosmos_client,
            settings=resolved_reader_settings,
        ),
    )


# La integración se hace sobre Definition para que servicios, middleware, callbacks y stores nazcan juntos.
# Sin Delivery igualmente materializamos stores desde la misma Tool Projection READY.
# Esto permite que callbacks de presentación produzcan UI degradada durante Authoring y Normal.
def attach_operational_kpi_presentation_stores(
    definition: WebApplicationDefinition,
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be WebApplicationDefinition')
    return attach_ada_kpi_presentation_stores(
        definition,
        structure=_resolve_operational_structure(tool_projection),
    )


def attach_operational_kpi_collector(
    definition: WebApplicationDefinition,
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
    cosmos_client: object,
    reader_settings: CosmosKpiDeliveryReaderSettings | None = None,
    polling_settings: KpiCollectorPollingSettings | None = None,
    presentation_settings: KpiCollectorPresentationSettings | None = None,
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be WebApplicationDefinition')
    collector = create_operational_kpi_collector(
        tool_projection=tool_projection,
        cosmos_client=cosmos_client,
        reader_settings=reader_settings,
    )
    return attach_ada_kpi_collector(
        definition,
        collector,
        polling_settings=polling_settings,
        presentation_settings=presentation_settings,
    )


# Centraliza la validación para que Collector con Delivery y stores sin Delivery nazcan del mismo contrato.
def _resolve_operational_structure(
    tool_projection: ProjectionRecord[ToolConfiguration],
) -> ToolStructure:
    if not isinstance(tool_projection, ProjectionRecord):
        raise TypeError('tool_projection must be a ProjectionRecord')
    configuration = tool_projection.payload
    if not isinstance(configuration, ToolConfiguration):
        raise TypeError('tool_projection payload must be ToolConfiguration')
    validate_ada_operational_tool_configuration(configuration)
    structure = configuration.structure
    if structure is None:
        raise ValueError('Operational Tool projection requires Tool Structure')
    return structure


# Construye el collector sin iniciar una conexión Cosmos durante el bootstrap.
def create_operational_alarm_collector(
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
    cosmos_client: object,
    reader_settings: AlarmLiveReaderSettings | None = None,
) -> AdaAlarmCollector:
    tool_key = _resolve_operational_structure(tool_projection).tool_key
    resolved_reader_settings = reader_settings or AlarmLiveReaderSettings()
    if not isinstance(resolved_reader_settings, AlarmLiveReaderSettings):
        raise TypeError('reader_settings must be AlarmLiveReaderSettings')
    return AdaAlarmCollector(
        tool_key=tool_key,
        reader=CosmosAlarmLiveReader(client=cosmos_client, settings=resolved_reader_settings),
    )


# Si Cosmos no está configurado, conserva el contrato de Store sin iniciar workers.
def attach_operational_alarm_presentation_store(
    definition: WebApplicationDefinition,
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be WebApplicationDefinition')
    return attach_ada_alarm_presentation_store(
        definition, tool_key=_resolve_operational_structure(tool_projection).tool_key,
    )


# Acopla el servicio de polling y el Store únicamente cuando existe conexión de consumo.
def attach_operational_alarm_collector(
    definition: WebApplicationDefinition,
    *,
    tool_projection: ProjectionRecord[ToolConfiguration],
    cosmos_client: object,
    reader_settings: AlarmLiveReaderSettings | None = None,
    polling_settings: AlarmCollectorPollingSettings | None = None,
    presentation_settings: AlarmCollectorPresentationSettings | None = None,
    can_view: Callable[[], bool] | None = None,
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('definition must be WebApplicationDefinition')
    collector = create_operational_alarm_collector(
        tool_projection=tool_projection,
        cosmos_client=cosmos_client,
        reader_settings=reader_settings,
    )
    return attach_ada_alarm_collector(
        definition,
        collector,
        polling_settings=polling_settings,
        presentation_settings=presentation_settings,
        can_view=can_view,
    )
