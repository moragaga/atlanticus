from __future__ import annotations

from dataclasses import dataclass

from ada.web.tools.configuration import (
    ToolConfiguration,
    ToolConfigurationProjectionError,
)
from ada.web.tools.persistence.composition import ToolPersistenceComposition
from ada.web.tools.persistence.models import ToolProjectionResolutionState
from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.connectivity.storage import StorageError
from atlanticus.web.projection.errors import (
    ProjectionError,
    ProjectionExecutionError,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.errors import (
    SourceError,
    SourceUnavailableError,
)
from atlanticus.web.source.models import SourceKey

DEFAULT_TOOL_SOURCE_KEY = SourceKey('tools')


@dataclass(frozen=True, slots=True)
class ToolProjectionResolution:
    state: ToolProjectionResolutionState
    projection: ProjectionRecord[ToolConfiguration] | None = None
    error_type: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, ToolProjectionResolutionState):
            raise TypeError('state must be ToolProjectionResolutionState')
        if self.state is ToolProjectionResolutionState.READY:
            if not isinstance(self.projection, ProjectionRecord):
                raise ValueError('READY resolution requires projection')
            if self.error_type is not None or self.message is not None:
                raise ValueError('READY resolution must not contain error diagnostics')
            return
        if self.projection is not None:
            raise ValueError('Non-READY resolution must not contain projection')
        has_error = self.error_type is not None or self.message is not None
        if self.state in {
            ToolProjectionResolutionState.UNAVAILABLE,
            ToolProjectionResolutionState.INVALID,
        }:
            if not has_error or self.error_type is None or self.message is None:
                raise ValueError('Failure resolution requires complete diagnostics')
        elif has_error:
            raise ValueError('UNCONFIGURED resolution must not contain diagnostics')


def resolve_active_tool_projection(
    composition: ToolPersistenceComposition,
    *,
    source_key: SourceKey = DEFAULT_TOOL_SOURCE_KEY,
) -> ToolProjectionResolution:
    _validate_inputs(composition, source_key)
    try:
        projection = composition.projection.get_active(source_key)
    except ToolConfigurationProjectionError as error:
        return _failure_resolution(error)
    except ProjectionError as error:
        return _invalid_resolution(error)

    if projection is None:
        return ToolProjectionResolution(
            state=ToolProjectionResolutionState.UNCONFIGURED,
        )
    if projection.source_key != source_key:
        return _invalid_message(
            'Projection store returned a different source key',
        )
    if not isinstance(projection.payload, ToolConfiguration):
        return _invalid_message(
            'Projection store returned a non-ToolConfiguration payload',
        )
    return ToolProjectionResolution(
        state=ToolProjectionResolutionState.READY,
        projection=projection,
    )


def project_current_tool_source(
    composition: ToolPersistenceComposition,
    *,
    source_key: SourceKey = DEFAULT_TOOL_SOURCE_KEY,
) -> ToolProjectionResolution:
    _validate_inputs(composition, source_key)
    try:
        target = composition.projection_service.select_current_target(source_key)
    except SourceUnavailableError as error:
        return _unavailable_resolution(error)
    except SourceError as error:
        return _invalid_resolution(error)

    if target is None:
        return ToolProjectionResolution(
            state=ToolProjectionResolutionState.UNCONFIGURED,
        )

    try:
        result = composition.projection_service.project(target)
    except ProjectionExecutionError as error:
        return _failure_resolution(error)
    except ProjectionError as error:
        return _invalid_resolution(error)

    return ToolProjectionResolution(
        state=ToolProjectionResolutionState.READY,
        projection=result.projection,
    )


def _validate_inputs(
    composition: ToolPersistenceComposition,
    source_key: SourceKey,
) -> None:
    if not isinstance(composition, ToolPersistenceComposition):
        raise TypeError('composition must be ToolPersistenceComposition')
    if not isinstance(source_key, SourceKey):
        raise TypeError('source_key must be SourceKey')


def _failure_resolution(error: BaseException) -> ToolProjectionResolution:
    if _contains_unavailable_cause(error):
        return _unavailable_resolution(error)
    return _invalid_resolution(error)


def _contains_unavailable_cause(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(
            current,
            (
                CosmosError,
                OSError,
                SourceUnavailableError,
                StorageError,
            ),
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _unavailable_resolution(error: BaseException) -> ToolProjectionResolution:
    return ToolProjectionResolution(
        state=ToolProjectionResolutionState.UNAVAILABLE,
        error_type=type(error).__name__,
        message=str(error),
    )


def _invalid_resolution(error: BaseException) -> ToolProjectionResolution:
    return ToolProjectionResolution(
        state=ToolProjectionResolutionState.INVALID,
        error_type=type(error).__name__,
        message=str(error),
    )


def _invalid_message(message: str) -> ToolProjectionResolution:
    return ToolProjectionResolution(
        state=ToolProjectionResolutionState.INVALID,
        error_type='ProjectionInvariantError',
        message=message,
    )
