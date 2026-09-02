from __future__ import annotations

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
    validate_operational_participation_against_consumption,
)
from ada.web.content_state.core import ContentState, SourceFreshnessCondition
from ada.web.content_state.dependency_resolver import (
    ContentStateDependency,
    ContentStateDependencyGraph,
)
from ada.web.time_status.store_adapter import (
    TimeStatusStoreSnapshot,
    TimeStatusTimestampQuality,
)
from ada.web.ui.time_status import (
    TimeStatusDetailState,
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSummaryState,
    resolve_time_status_source_state,
)

from .models import AdaOperationalState

_SUPPORTED_CONTENT_STATE_COMPONENT_KEYS = frozenset({'global_indicators'})
_SUPPORTED_ADA_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})
_TIME_STATUS_SOURCE_LABELS = {'pi': 'PI', 'dispatch': 'Dispatch'}
_TIME_STATUS_FRESHNESS = {
    TimeStatusSourceCondition.FRESH: SourceFreshnessCondition.FRESH,
    TimeStatusSourceCondition.PREVENTIVE: SourceFreshnessCondition.PREVENTIVE,
    TimeStatusSourceCondition.HARD_STALE: SourceFreshnessCondition.HARD_STALE,
    TimeStatusSourceCondition.DATA_ERROR: SourceFreshnessCondition.DATA_ERROR,
}


def resolve_ada_operational_state(
    *,
    has_global_indicators: bool,
    content_state_dependencies: tuple[ContentStateDependency, ...] = (),
    source_consumption: ToolSourceConsumption | None = None,
    source_operational_participation: ToolSourceOperationalParticipation | None = None,
    time_status_snapshot: TimeStatusStoreSnapshot | None = None,
    time_status_detail: TimeStatusDetailState | None = None,
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
        time_status_snapshot=time_status_snapshot,
        time_status_detail=time_status_detail,
    )
    time_status_summary = _resolve_time_status_summary(
        snapshot=time_status_snapshot,
        participation=source_operational_participation,
    )
    source_conditions = _resolve_source_freshness(time_status_summary)
    resolved_content_states = (
        dependency_graph.resolve(source_conditions) if dependency_graph.dependencies else {}
    )
    return AdaOperationalState(
        tool_key=source_consumption.tool_key if source_consumption is not None else None,
        time_status_summary=time_status_summary,
        global_indicators_runtime_state=resolved_content_states.get(
            'global_indicators',
            ContentState.READY,
        ),
        global_indicators_source_keys=dependency_graph.sources_for_component('global_indicators'),
    )


def _validate_source_configuration(
    *,
    source_consumption: ToolSourceConsumption | None,
    participation: ToolSourceOperationalParticipation | None,
    dependency_graph: ContentStateDependencyGraph,
    time_status_snapshot: TimeStatusStoreSnapshot | None,
    time_status_detail: TimeStatusDetailState | None,
) -> None:
    source_driven = bool(
        dependency_graph.dependencies
        or time_status_snapshot is not None
        or time_status_detail is not None
    )
    if source_driven and source_consumption is None:
        raise ToolSourceConsumptionValidationError(
            'Source-driven Generic Application composition requires ToolSourceConsumption'
        )
    if source_driven and participation is None:
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
        time_status_detail=time_status_detail,
    )
    _validate_ada_operational_participation(
        source_consumption=source_consumption,
        participation=participation,
    )
    if (
        time_status_snapshot is not None
        and time_status_snapshot.tool_key != source_consumption.tool_key
    ):
        raise ToolSourceOperationalParticipationValidationError(
            'Time Status snapshot tool key must match Tool Source Consumption tool key'
        )
    if time_status_detail is not None and time_status_snapshot is None:
        raise ToolSourceOperationalParticipationValidationError(
            'Time Status detail requires Time Status snapshot'
        )
    _validate_observation_detail(
        detail=time_status_detail,
        participation=participation,
    )
    _validate_control_dependencies(
        graph=dependency_graph,
        participation=participation,
    )


def _validate_runtime_source_membership(
    *,
    source_consumption: ToolSourceConsumption,
    dependency_graph: ContentStateDependencyGraph,
    time_status_detail: TimeStatusDetailState | None,
) -> None:
    required_source_keys: list[str] = []
    if time_status_detail is not None:
        required_source_keys.extend(source.key for source in time_status_detail.sources)
    for dependency in dependency_graph.dependencies:
        required_source_keys.extend(dependency.source_keys)

    declared_source_keys = set(source_consumption.source_keys)
    for source_key in dict.fromkeys(required_source_keys):
        if source_key not in declared_source_keys:
            raise ToolSourceConsumptionValidationError(
                f'Source is not declared by Tool Configuration: {source_key!r}'
            )


def _validate_ada_operational_participation(
    *,
    source_consumption: ToolSourceConsumption,
    participation: ToolSourceOperationalParticipation,
) -> None:
    if 'pi' not in source_consumption.source_keys:
        raise ToolSourceConsumptionValidationError(
            "Source is not declared by Tool Configuration: 'pi'"
        )
    if not participation.controls('pi'):
        raise ToolSourceOperationalParticipationValidationError(
            'ADA Generic Application requires PI as a CONTROL source'
        )
    unsupported = tuple(
        source_key
        for source_key in participation.control_source_keys
        if source_key not in _SUPPORTED_ADA_CONTROL_SOURCE_KEYS
    )
    if unsupported:
        raise ToolSourceOperationalParticipationValidationError(
            'ADA Generic Application supports only PI and Dispatch as CONTROL sources: '
            f'{unsupported[0]!r}'
        )
    if 'dispatch' in source_consumption.source_keys and not participation.controls('dispatch'):
        raise ToolSourceOperationalParticipationValidationError(
            'Dispatch declared by Tool Source Consumption must participate as CONTROL'
        )


def _validate_observation_detail(
    *,
    detail: TimeStatusDetailState | None,
    participation: ToolSourceOperationalParticipation,
) -> None:
    if detail is None:
        return
    additional_observation_source_keys = set(participation.additional_observation_source_keys)
    for source in detail.sources:
        if source.key not in additional_observation_source_keys:
            raise ToolSourceOperationalParticipationValidationError(
                'Time Status detail source is not declared as ADDITIONAL OBSERVATION: '
                f'{source.key!r}'
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


def _resolve_time_status_summary(
    *,
    snapshot: TimeStatusStoreSnapshot | None,
    participation: ToolSourceOperationalParticipation | None,
) -> TimeStatusSummaryState | None:
    if snapshot is None:
        return None
    if participation is None:
        raise ToolSourceOperationalParticipationValidationError(
            'Time Status snapshot requires ToolSourceOperationalParticipation'
        )
    pi_policy = participation.control_policy('pi')
    if pi_policy is None:
        raise ToolSourceOperationalParticipationValidationError(
            'ADA Generic Application requires PI as a CONTROL source'
        )
    dispatch_policy = participation.control_policy('dispatch')
    return TimeStatusSummaryState(
        pi=_resolve_time_status_control_source(snapshot=snapshot, policy=pi_policy),
        dispatch=(
            None
            if dispatch_policy is None
            else _resolve_time_status_control_source(snapshot=snapshot, policy=dispatch_policy)
        ),
        has_detail=True,
    )


def _resolve_time_status_control_source(
    *,
    snapshot: TimeStatusStoreSnapshot,
    policy: SourceControlPolicy,
):
    timestamp = snapshot.source(policy.source_key)
    return resolve_time_status_source_state(
        key=policy.source_key,
        label=_TIME_STATUS_SOURCE_LABELS[policy.source_key],
        policy=TimeStatusFreshnessPolicy(
            warning_after_seconds=policy.pre_degrading_after_seconds,
            stale_after_seconds=policy.degrading_after_seconds,
        ),
        timestamp_utc=(
            timestamp.timestamp_utc
            if timestamp.quality is TimeStatusTimestampQuality.VALID
            else None
        ),
        now_utc=snapshot.generated_at_utc,
    )


def _resolve_source_freshness(
    summary: TimeStatusSummaryState | None,
) -> dict[str, SourceFreshnessCondition]:
    if summary is None:
        return {}
    return {
        source.key: _TIME_STATUS_FRESHNESS[source.condition] for source in summary.required_sources
    }


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
