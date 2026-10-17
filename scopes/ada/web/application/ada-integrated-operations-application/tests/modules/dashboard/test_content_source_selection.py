from __future__ import annotations

import pytest

from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.card import (
    build_component_panel,
    build_shared_dashboard_card,
)
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
    DashboardSharedCardBinding,
    OperationalControlSource,
)
from ada.web.application.integrated_operations.modules.dashboard.global_indicators.bindings import (
    DashboardGlobalIndicatorBinding,
)
from ada.web.content_state import ContentState
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorMeasurementDefinition,
)


def _props(node):
    return node.to_plotly_json()['props']


def _walk(node):
    yield node
    children = _props(node).get('children')
    if not isinstance(children, list | tuple):
        children = (children,)
    for child in children:
        if hasattr(child, 'to_plotly_json'):
            yield from _walk(child)


def _component_card(source_keys):
    card = DashboardCardBinding(
        key='sample', label='Sample', tool_subcomponent_key='sub', source_keys=source_keys,
    )
    component = DashboardComponentBinding(
        key='cmp', label='Component', scope=ToolScope.MINE,
        tool_component_key='component_key', cards=(card,),
    )
    panel = build_component_panel(component)
    return next(node for node in _walk(panel)
                if _props(node).get('data-ada-content-state-operational') == 'true')


@pytest.mark.parametrize('sources,expected', [
    ((OperationalControlSource.PI,), 'pi'),
    ((OperationalControlSource.DISPATCH,), 'dispatch'),
    ((OperationalControlSource.PI, OperationalControlSource.DISPATCH), 'pi,dispatch'),
    ((), ''),
])
def test_card_projects_explicit_dependency(sources, expected):
    assert _props(_component_card(sources))['data-ada-content-state-sources'] == expected


def test_unclassified_card_does_not_silently_claim_independence():
    assert 'data-ada-content-state-sources' not in _props(_component_card(None))


def test_shared_card_projects_own_dependencies():
    wrapper = build_shared_dashboard_card(DashboardSharedCardBinding(
        key='shared', label='Shared', scope=ToolScope.MINE,
        tool_component_key='owner', tool_subcomponent_key='sub',
        linked_tool_component_keys=('linked',),
        source_keys=(OperationalControlSource.PI, OperationalControlSource.DISPATCH),
    ))
    assert _props(wrapper)['data-ada-content-state-sources'] == 'pi,dispatch'


def test_construction_card_remains_construction():
    card = DashboardCardBinding(
        key='construction', label='Construction', tool_subcomponent_key='sub',
        content_state=ContentState.CONSTRUCTION, source_keys=(OperationalControlSource.PI,),
    )
    panel = build_component_panel(DashboardComponentBinding(
        key='cmp', label='Component', scope=ToolScope.MINE,
        tool_component_key='owner', cards=(card,),
    ))
    wrapper = next(node for node in _walk(panel)
                   if _props(node).get('data-ada-content-state-operational') == 'true')
    assert _props(wrapper)['data-ada-content-state'] == 'construction'


@pytest.mark.parametrize('sources', [
    (OperationalControlSource.PI, OperationalControlSource.PI),
    ('pi',),
    ('unknown',),
    ['pi'],
    (ToolScope.MINE,),
])
def test_invalid_sources_are_rejected_in_card_contract(sources):
    with pytest.raises((TypeError, ValueError)):
        DashboardCardBinding('card', 'Card', 'sub', source_keys=sources)


def test_global_indicator_preserves_scopes_with_explicit_sources():
    definition = GlobalIndicatorDefinition(
        key='sample', label='Sample', unit='t',
        measurements=(
            GlobalIndicatorMeasurementDefinition(
                key='day', label='Day', actual_kpi_key='real', plan_kpi_key='plan',
            ),
            GlobalIndicatorMeasurementDefinition(
                key='week', label='Week', actual_kpi_key='week_real',
                plan_kpi_key='week_plan',
            ),
        ),
    )
    binding = DashboardGlobalIndicatorBinding(
        definition, (ToolScope.MINE, ToolScope.PLANT),
        source_keys=(OperationalControlSource.PI,),
    )
    assert binding.appears_in(ToolScope.MINE)
    assert binding.appears_in(ToolScope.PLANT)
    assert binding.source_keys == (OperationalControlSource.PI,)


def test_global_indicator_rejects_string_source_keys():
    definition = GlobalIndicatorDefinition(
        key='sample', label='Sample', unit='t',
        measurements=(
            GlobalIndicatorMeasurementDefinition(
                key='day', label='Day', actual_kpi_key='real', plan_kpi_key='plan',
            ),
            GlobalIndicatorMeasurementDefinition(
                key='week', label='Week', actual_kpi_key='week_real',
                plan_kpi_key='week_plan',
            ),
        ),
    )
    with pytest.raises(TypeError, match='OperationalControlSource'):
        DashboardGlobalIndicatorBinding(
            definition, (ToolScope.MINE,), source_keys=('pi',),
        )


def test_enum_values_match_operational_freshness_event_keys():
    assert OperationalControlSource.PI.value == 'pi'
    assert OperationalControlSource.DISPATCH.value == 'dispatch'
