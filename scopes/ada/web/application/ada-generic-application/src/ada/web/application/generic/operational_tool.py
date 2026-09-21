from __future__ import annotations

import logging

from ada.web.application.generic.runtime import create_application_runtime
from ada.web.tools.configuration import validate_ada_operational_tool_configuration
from ada.web.tools.errors import ToolConfigurationValidationError
from ada.web.tools.persistence import (
    ToolPersistenceComposition,
    ToolProjectionResolution,
    ToolProjectionResolutionState,
    resolve_active_tool_projection,
)
from atlanticus.web.models import WebApplicationRuntime

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


def create_runtime_from_tool_resolution(
    resolution: ToolProjectionResolution,
) -> WebApplicationRuntime:
    if not isinstance(resolution, ToolProjectionResolution):
        raise TypeError('resolution must be ToolProjectionResolution')
    if resolution.state is ToolProjectionResolutionState.READY:
        projection = resolution.projection
        if projection is None:
            raise RuntimeError('READY Tool Projection resolution has no projection')
        configuration = projection.payload
        return create_application_runtime(
            tool_display_name=configuration.display_name,
            branding_configuration=configuration.branding,
            source_consumption=configuration.source_consumption,
            source_operational_participation=configuration.source_operational_participation,
        )
    _log_degraded_resolution(resolution)
    return create_application_runtime()


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
