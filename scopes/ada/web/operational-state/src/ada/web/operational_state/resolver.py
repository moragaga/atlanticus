from __future__ import annotations

from ada.contracts.tools.sources import (
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
    validate_operational_participation_against_consumption,
)
from ada.web.content_state import (
    ContentState,
    ContentStateDependency,
    ContentStateDependencyGraph,
)

from .models import AdaOperationalState

_SUPPORTED_CONTENT_STATE_COMPONENT_KEYS = frozenset({'global_indicators'})


def resolve_ada_operational_state(
    *,
    has_global_indicators: bool,
    content_state_dependencies: tuple[ContentStateDependency, ...] = (),
    source_consumption: ToolSourceConsumption | None = None,
    source_operational_participation: ToolSourceOperationalParticipation | None = None,
) -> AdaOperationalState:
    dependency_graph = ContentStateDependencyGraph(content_state_dependencies)
    _validate_content_state_dependencies(
        dependency_graph,
        has_global_indicators=has_global_indicators,
    )
    _validate_source_configuration(
        source_consumption=source_consumption,
        participation=source_operational_participation,
        dependency_graph=dependency_graph,
    )
    return AdaOperationalState(
        tool_key=source_consumption.tool_key if source_consumption is not None else None,
        global_indicators_runtime_state=ContentState.READY,
        global_indicators_source_keys=dependency_graph.sources_for_component('global_indicators'),
    )


def _validate_source_configuration(
    *,
    source_consumption: ToolSourceConsumption | None,
    participation: ToolSourceOperationalParticipation | None,
    dependency_graph: ContentStateDependencyGraph,
) -> None:
    if dependency_graph.dependencies and source_consumption is None:
        raise ToolSourceConsumptionValidationError(
            'Source-driven Generic Application composition requires ToolSourceConsumption'
        )
    if dependency_graph.dependencies and participation is None:
        raise ToolSourceOperationalParticipationValidationError(
            'Source-driven Generic Application composition requires '
            'ToolSourceOperationalParticipation'
        )
    if participation is None:
        return
    if source_consumption is None:
        raise ToolSourceConsumptionValidationError(
            'ToolSourceOperationalParticipation requires ToolSourceConsumption'
        )

    validate_operational_participation_against_consumption(
        consumption=source_consumption,
        participation=participation,
    )
    _validate_runtime_source_membership(
        source_consumption=source_consumption,
        dependency_graph=dependency_graph,
    )
    _validate_control_dependencies(
        graph=dependency_graph,
        participation=participation,
    )


def _validate_runtime_source_membership(
    *,
    source_consumption: ToolSourceConsumption,
    dependency_graph: ContentStateDependencyGraph,
) -> None:
    declared_source_keys = set(source_consumption.source_keys)
    for dependency in dependency_graph.dependencies:
        for source_key in dependency.source_keys:
            if source_key not in declared_source_keys:
                raise ToolSourceConsumptionValidationError(
                    f'Source is not declared by Tool Configuration: {source_key!r}'
                )


def _validate_control_dependencies(
    *,
    graph: ContentStateDependencyGraph,
    participation: ToolSourceOperationalParticipation,
) -> None:
    control_source_keys = set(participation.control_source_keys)
    for dependency in graph.dependencies:
        for source_key in dependency.source_keys:
            if source_key not in control_source_keys:
                raise ToolSourceOperationalParticipationValidationError(
                    f'Content State dependency source is not declared as CONTROL: {source_key!r}'
                )


def _validate_content_state_dependencies(
    graph: ContentStateDependencyGraph,
    *,
    has_global_indicators: bool,
) -> None:
    unsupported = tuple(
        dependency.component_key
        for dependency in graph.dependencies
        if dependency.component_key not in _SUPPORTED_CONTENT_STATE_COMPONENT_KEYS
    )
    if unsupported:
        raise ValueError(
            f'Unsupported Generic Application Content State component: {unsupported[0]!r}'
        )
    if graph.sources_for_component('global_indicators') and not has_global_indicators:
        raise ValueError('Global Indicators Content State dependency requires Global Indicators')
