from __future__ import annotations

from types import MappingProxyType

import pytest

from ada.web.content_state.core import ContentState, SourceFreshnessCondition
from ada.web.content_state.dependency_resolver import (
    ContentStateDependency,
    ContentStateDependencyError,
    ContentStateDependencyGraph,
    MissingSourceFreshnessError,
)


def _global_indicator_graph(*sources: str) -> ContentStateDependencyGraph:
    return ContentStateDependencyGraph(
        (
            ContentStateDependency(
                component_key='global_indicators',
                source_keys=tuple(sources),
            ),
        )
    )


def test_graph_exposes_reverse_source_to_component_index() -> None:
    graph = ContentStateDependencyGraph(
        (
            ContentStateDependency('global_indicators', ('pi',)),
            ContentStateDependency('dispatch_summary', ('dispatch',)),
            ContentStateDependency('integrated_panel', ('pi', 'dispatch')),
        )
    )

    assert graph.components_for_source('pi') == ('global_indicators', 'integrated_panel')
    assert graph.components_for_source('dispatch') == ('dispatch_summary', 'integrated_panel')
    assert graph.sources_for_component('integrated_panel') == ('pi', 'dispatch')
    assert graph.sources_for_component('unknown_component') == ()


def test_graph_rejects_duplicate_component_definition() -> None:
    with pytest.raises(
        ContentStateDependencyError, match='Duplicate Content State component dependency'
    ):
        ContentStateDependencyGraph(
            (
                ContentStateDependency('global_indicators', ('pi',)),
                ContentStateDependency('global_indicators', ('dispatch',)),
            )
        )


def test_graph_rejects_non_dependency_values() -> None:
    with pytest.raises(TypeError, match='requires ContentStateDependency values'):
        ContentStateDependencyGraph(('global_indicators',))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ('condition', 'expected'),
    (
        (SourceFreshnessCondition.FRESH, ContentState.READY),
        (SourceFreshnessCondition.PREVENTIVE, ContentState.READY),
        (SourceFreshnessCondition.HARD_STALE, ContentState.STALE),
        (SourceFreshnessCondition.DATA_ERROR, ContentState.SOURCE_ERROR),
    ),
)
def test_graph_resolves_single_pi_dependency_from_cs003_policy(
    condition: SourceFreshnessCondition,
    expected: ContentState,
) -> None:
    graph = _global_indicator_graph('pi')

    resolved = graph.resolve({'pi': condition})

    assert isinstance(resolved, MappingProxyType)
    assert resolved == {'global_indicators': expected}


def test_component_with_pi_and_dispatch_uses_its_own_or_semantics() -> None:
    graph = _global_indicator_graph('pi', 'dispatch')

    assert graph.resolve(
        {
            'pi': SourceFreshnessCondition.HARD_STALE,
            'dispatch': SourceFreshnessCondition.FRESH,
        }
    ) == {'global_indicators': ContentState.STALE}
    assert graph.resolve(
        {
            'pi': SourceFreshnessCondition.FRESH,
            'dispatch': SourceFreshnessCondition.DATA_ERROR,
        }
    ) == {'global_indicators': ContentState.SOURCE_ERROR}


def test_source_error_wins_over_stale_across_component_dependencies() -> None:
    graph = _global_indicator_graph('pi', 'dispatch')

    assert graph.resolve(
        {
            'pi': SourceFreshnessCondition.HARD_STALE,
            'dispatch': SourceFreshnessCondition.DATA_ERROR,
        }
    ) == {'global_indicators': ContentState.SOURCE_ERROR}


def test_missing_required_source_condition_fails_explicitly() -> None:
    graph = _global_indicator_graph('pi', 'dispatch')

    with pytest.raises(MissingSourceFreshnessError, match="required source: 'dispatch'"):
        graph.resolve({'pi': SourceFreshnessCondition.FRESH})


def test_extra_supported_control_condition_is_allowed_when_not_referenced() -> None:
    graph = _global_indicator_graph('pi')

    assert graph.resolve(
        {
            'pi': SourceFreshnessCondition.FRESH,
            'dispatch': SourceFreshnessCondition.DATA_ERROR,
        }
    ) == {'global_indicators': ContentState.READY}


def test_informational_source_cannot_enter_resolution_snapshot() -> None:
    graph = _global_indicator_graph('pi')

    with pytest.raises(
        ContentStateDependencyError, match='Unsupported Content State control source'
    ):
        graph.resolve(
            {
                'pi': SourceFreshnessCondition.FRESH,
                'blockgrade': SourceFreshnessCondition.DATA_ERROR,
            }
        )


def test_resolver_rejects_implicit_condition_string_coercion() -> None:
    graph = _global_indicator_graph('pi')

    with pytest.raises(TypeError, match='requires SourceFreshnessCondition values'):
        graph.resolve({'pi': 'hard_stale'})  # type: ignore[dict-item]


def test_empty_graph_resolves_to_empty_read_only_mapping() -> None:
    resolved = ContentStateDependencyGraph().resolve({})

    assert isinstance(resolved, MappingProxyType)
    assert dict(resolved) == {}
