from __future__ import annotations

import logging

from ada.contracts.tools.errors import ToolConfigurationValidationError
from ada.web.alarms.baseline_projection import project_alarm_baseline
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.composition import AdaApplicationComposition
from ada.web.application.generic.descriptor import AdaApplicationDescriptor
from ada.web.operational_render_binding import (
    OperationalRenderBinding,
    bind_operational_render,
)
from ada.web.tools.configuration import validate_ada_operational_tool_configuration
from ada.web.tools.persistence import (
    ToolPersistenceComposition,
    ToolProjectionResolution,
    ToolProjectionResolutionState,
    resolve_active_tool_projection,
)
from atlanticus.web.models import WebApplicationDefinition

_LOGGER = logging.getLogger(__name__)


def resolve_operational_tool_projection(
    composition: ToolPersistenceComposition,
) -> ToolProjectionResolution:
    resolution = resolve_active_tool_projection(composition)
    if resolution.state is not ToolProjectionResolutionState.READY:
        return resolution
    projection = resolution.projection
    if projection is None:
        return ToolProjectionResolution(
            state=ToolProjectionResolutionState.INVALID,
            error_type='ProjectionInvariantError',
            message='READY Tool Projection resolution has no projection',
        )
    try:
        validate_ada_operational_tool_configuration(projection.payload)
    except ToolConfigurationValidationError as error:
        return ToolProjectionResolution(
            state=ToolProjectionResolutionState.INVALID,
            error_type=type(error).__name__,
            message=str(error),
        )
    return resolution


def resolve_operational_render_binding(
    resolution: ToolProjectionResolution,
) -> OperationalRenderBinding | None:
    if not isinstance(resolution, ToolProjectionResolution):
        raise TypeError('resolution must be ToolProjectionResolution')
    if resolution.state is not ToolProjectionResolutionState.READY:
        return None
    projection = resolution.projection
    if projection is None:
        raise RuntimeError('READY Tool Projection resolution has no projection')
    configuration = projection.payload
    structure = configuration.structure
    if structure is None:
        raise RuntimeError('READY Tool Projection has no Tool Structure')
    return bind_operational_render(
        structure,
        bottom_component_key=configuration.render_topology.bottom_component_key,
    )


def create_definition_from_tool_resolution(
    resolution: ToolProjectionResolution,
    *,
    application_descriptor: AdaApplicationDescriptor | None = None,
    composition: AdaApplicationComposition | None = None,
    operational_render_binding: OperationalRenderBinding | None = None,
) -> WebApplicationDefinition:
    if not isinstance(resolution, ToolProjectionResolution):
        raise TypeError('resolution must be ToolProjectionResolution')
    definition_options: dict[str, object] = {}
    if application_descriptor is not None:
        definition_options['application_descriptor'] = application_descriptor
    if composition is not None:
        definition_options['composition'] = composition
    if (
        operational_render_binding is not None
        and composition is not None
        and composition.operational_body_factory is not None
    ):
        definition_options['operational_render_binding'] = operational_render_binding
    if resolution.state is ToolProjectionResolutionState.READY:
        projection = resolution.projection
        if projection is None:
            raise RuntimeError('READY Tool Projection resolution has no projection')
        configuration = projection.payload
        structure = configuration.structure
        if structure is None:
            raise RuntimeError('READY Tool Projection has no Tool Structure')
        bottom_component_key = configuration.render_topology.bottom_component_key
        baseline_binding = operational_render_binding
        if baseline_binding is None:
            baseline_binding = resolve_operational_render_binding(resolution)
        elif (
            baseline_binding.structure != structure
            or baseline_binding.bottom_component_key != bottom_component_key
        ):
            raise ValueError('Operational render binding must match Tool Projection')
        if baseline_binding is None:
            raise RuntimeError('READY Tool Projection has no Operational Render Binding')
        alarm_baseline_projection = project_alarm_baseline(
            baseline_binding.structure,
            bottom_component_key=baseline_binding.bottom_component_key,
        )
        return create_application_definition(
            **definition_options,
            tool_display_name=configuration.display_name,
            branding_configuration=configuration.branding,
            alarm_baseline_projection=alarm_baseline_projection,
            source_consumption=configuration.source_consumption,
            source_operational_participation=configuration.source_operational_participation,
        )
    _log_degraded_resolution(resolution)
    return create_application_definition(**definition_options)


def _log_degraded_resolution(resolution: ToolProjectionResolution) -> None:
    if resolution.state is ToolProjectionResolutionState.UNCONFIGURED:
        _LOGGER.info('Operational Tool is not configured')
        return
    if resolution.state is ToolProjectionResolutionState.UNAVAILABLE:
        _LOGGER.warning(
            'Operational Tool is unavailable (%s): %s',
            resolution.error_type,
            resolution.message,
        )
        return
    _LOGGER.error(
        'Operational Tool configuration is invalid (%s): %s',
        resolution.error_type,
        resolution.message,
    )
