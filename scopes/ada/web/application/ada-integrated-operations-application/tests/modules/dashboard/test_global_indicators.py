from __future__ import annotations

import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.application.integrated_operations import create_integrated_operations_extension
from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    GLOBAL_INDICATORS_DESTINATION_KEY,
    DashboardGlobalIndicatorBinding,
    DashboardGlobalIndicatorsRuntimeBinding,
    build_dashboard_global_indicators_runtime_component,
    create_dashboard_global_indicators_module,
    resolve_dashboard_global_indicators,
)
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    OperationalControlSource,
)
from ada.web.content_state import ContentState
from ada.web.kpis.collector import system_kpi_store_id
from ada.web.operational_render_binding import bind_operational_render
from ada.web.shell.header import GLOBAL_INDICATORS_SLOT_ID
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorLastMeasurementDefinition,
    GlobalIndicatorMeasurementDefinition,
)


class DashStub:
    def __init__(self) -> None:
        self.callback_args = ()
        self.callback_function = None

    def callback(self, *args, **_kwargs):
        self.callback_args = args

        def register(function):
            self.callback_function = function
            return function

        return register


def _definition(key: str) -> GlobalIndicatorDefinition:
    return GlobalIndicatorDefinition(
        key=key,
        label=key.replace('_', ' ').title(),
        unit='u',
        measurements=(
            GlobalIndicatorMeasurementDefinition(
                key='turno',
                label='Turno',
                actual_kpi_key=f'{key}.turno.actual',
                plan_kpi_key=f'{key}.turno.plan',
                color_kpi_key=f'{key}.turno.color',
            ),
            GlobalIndicatorMeasurementDefinition(
                key='dia',
                label='Día',
                actual_kpi_key=f'{key}.dia.actual',
                plan_kpi_key=f'{key}.dia.plan',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementDefinition(
            kpi_key=f'{key}.latest',
        ),
    )


def _binding(
    *,
    content_state: ContentState = ContentState.READY,
) -> DashboardGlobalIndicatorsRuntimeBinding:
    return DashboardGlobalIndicatorsRuntimeBinding(
        tool_key='integrated_operations',
        indicators=(
            DashboardGlobalIndicatorBinding(
                _definition('mine_only'), (ToolScope.MINE,), source_keys=(OperationalControlSource.DISPATCH,),
            ),
            DashboardGlobalIndicatorBinding(
                _definition('shared'), (ToolScope.MINE, ToolScope.PLANT),
                source_keys=(OperationalControlSource.PI, OperationalControlSource.DISPATCH),
            ),
            DashboardGlobalIndicatorBinding(
                _definition('plant_only'), (ToolScope.PLANT,), source_keys=(OperationalControlSource.PI,),
            ),
        ),
        content_state=content_state,
    )


def _ok(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def _store() -> dict[str, object]:
    values = {}
    for key in ('mine_only', 'shared', 'plant_only'):
        values.update(
            {
                f'{key}.turno.actual': _ok(10),
                f'{key}.turno.plan': _ok(12),
                f'{key}.turno.color': _ok('indicator-positive'),
                f'{key}.dia.actual': _ok(20),
                f'{key}.dia.plan': _ok(24),
                f'{key}.latest': _ok(22),
            }
        )
    return {
        'tool_key': 'integrated_operations',
        'destination_key': 'global_indicators',
        'latest': {'manifest': {'revision': 'r1'}, 'values': values},
        'timeseries': None,
    }


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = _props(component).get('children')
    if hasattr(children, 'to_plotly_json'):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'to_plotly_json'):
                yield from _walk(child)


def _states(component):
    placements = (
        node for node in _walk(component) if _props(node).get('data-ada-io-global-indicator-key')
    )
    return {
        _props(placement)['data-ada-io-global-indicator-key']: next(
            _props(child)
            for child in _walk(placement)
            if _props(child).get('data-ada-content-state-operational') == 'true'
        )
        for placement in placements
    }


def test_binding_supports_shared_indicator_and_collection_level_content_state() -> None:
    binding = _binding()
    assert binding.content_state is ContentState.READY
    assert binding.indicators[1].appears_in(ToolScope.MINE)
    assert binding.indicators[1].appears_in(ToolScope.PLANT)
    assert tuple(item.definition.key for item in binding.indicators) == (
        'mine_only', 'shared', 'plant_only',
    )


def test_binding_rejects_duplicate_indicator_identity_scopes_and_invalid_content_state() -> None:
    definition = _definition('shared')
    with pytest.raises(ValueError, match='presentation scopes must be unique'):
        DashboardGlobalIndicatorBinding(definition, (ToolScope.MINE, ToolScope.MINE))

    shared = DashboardGlobalIndicatorBinding(definition, (ToolScope.MINE, ToolScope.PLANT))
    with pytest.raises(ValueError, match='unique indicator keys'):
        DashboardGlobalIndicatorsRuntimeBinding('integrated_operations', (shared, shared))
    with pytest.raises(TypeError, match='content_state'):
        DashboardGlobalIndicatorsRuntimeBinding(
            'integrated_operations', (shared,), content_state='construction',
        )


def test_resolver_maps_canonical_latest_envelopes_and_preserves_kpi_inspection_keys() -> None:
    resolved = resolve_dashboard_global_indicators(_store(), binding=_binding())
    shared = resolved[1].state
    assert shared.key == 'shared'
    assert shared.measurements[0].actual_value.status is DisplayStatus.OK
    assert shared.measurements[0].actual_value.value == '10'
    assert shared.measurements[0].actual_kpi_key == 'shared.turno.actual'
    assert shared.measurements[0].color_class == 'indicator-positive'
    assert shared.last_measurement is not None
    assert shared.last_measurement.actual_kpi_key == 'shared.latest'


def test_missing_kpi_only_degrades_its_own_display_value() -> None:
    store = _store()
    del store['latest']['values']['shared.dia.plan']

    resolved = resolve_dashboard_global_indicators(store, binding=_binding())
    assert resolved[1].state.measurements[1].plan_value.status is DisplayStatus.NOT_MAPPED
    assert resolved[0].state.measurements[1].plan_value.status is DisplayStatus.OK
    assert resolved[2].state.measurements[1].plan_value.status is DisplayStatus.OK


def test_invalid_latest_is_represented_as_display_status_not_content_state() -> None:
    resolved = resolve_dashboard_global_indicators(None, binding=_binding())
    assert all(item.state.measurements[0].actual_value.status is DisplayStatus.INVALID
               for item in resolved)
    store = _store()
    store['latest']['values']['shared.turno.actual'] = {
        'status': 'ok',
        'value_kind': 'json',
        'value': {'value': 10},
        'value_type': None,
        'parsed_value': None,
    }
    resolved = resolve_dashboard_global_indicators(store, binding=_binding())
    assert resolved[1].state.measurements[0].actual_value.status is DisplayStatus.INVALID


def test_runtime_renders_each_indicator_once_and_shared_scope_metadata_once() -> None:
    component = build_dashboard_global_indicators_runtime_component(_store(), binding=_binding())
    placements = [
        node for node in _walk(component) if _props(node).get('data-ada-io-global-indicator-key')
    ]
    assert len(placements) == 3
    shared = next(node for node in placements if _props(node)['data-ada-io-global-indicator-key'] == 'shared')
    assert _props(shared)['data-ada-io-global-indicator-scopes'] == 'mine,plant'
    assert _props(shared)['data-ada-io-scope-mine'] == 'true'
    assert _props(shared)['data-ada-io-scope-plant'] == 'true'
    states = _states(component)
    assert states['mine_only']['data-ada-content-state-sources'] == 'dispatch'
    assert states['shared']['data-ada-content-state-sources'] == 'pi,dispatch'
    assert states['plant_only']['data-ada-content-state-sources'] == 'pi'




def test_header_host_keeps_layout_but_ignores_global_source_freshness() -> None:
    component = build_dashboard_global_indicators_runtime_component(_store(), binding=_binding())
    props = _props(component)

    assert props['data-ada-content-state-operational'] == 'true'
    assert props['data-ada-content-state-sources'] == ''
    assert props['data-ada-content-state'] == 'ready'
    assert len(_states(component)) == 3

def test_runtime_callback_bridges_exact_system_store_to_header_slot() -> None:
    binding = _binding()
    module = create_dashboard_global_indicators_module(binding)
    dash_app = DashStub()
    module.register_callbacks(dash_app, object())

    component, empty, ready = dash_app.callback_function(_store())
    grids = [node for node in _walk(component)
             if _props(node).get('data-ada-io-global-indicators-runtime') == 'true']
    assert module.name == 'ada-integrated-operations-global-indicators'
    assert module.asset_layers == ()
    assert empty == 'false'
    assert ready == 'true'
    assert len(grids) == 1
    assert all(state['data-ada-content-state'] == 'ready' for state in _states(component).values())
    assert system_kpi_store_id('integrated_operations', GLOBAL_INDICATORS_DESTINATION_KEY) == {
        'type': 'ada-kpi-system-store',
        'tool': 'integrated_operations',
        'destination': 'global_indicators',
    }
    outputs = dash_app.callback_args[:3]
    assert all(output.component_id == GLOBAL_INDICATORS_SLOT_ID for output in outputs)


def test_runtime_callback_keeps_content_state_ready_with_empty_system_store() -> None:
    binding = _binding()
    module = create_dashboard_global_indicators_module(binding)
    dash_app = DashStub()
    module.register_callbacks(dash_app, object())

    component, empty, ready = dash_app.callback_function({
        'tool_key': 'integrated_operations',
        'destination_key': 'global_indicators',
        'latest': None,
        'timeseries': None,
    })
    assert empty == 'false'
    assert ready == 'true'
    assert len(_states(component)) == 3
    assert all(state['data-ada-content-state'] == 'ready'
               for state in _states(component).values())
    assert all(state['data-ada-content-state-declared'] == 'ready'
               for state in _states(component).values())


def test_individual_invalid_kpi_does_not_override_temporal_content_state() -> None:
    store = _store()
    del store['latest']['values']['shared.dia.plan']
    states = _states(build_dashboard_global_indicators_runtime_component(store, binding=_binding()))
    assert states['mine_only']['data-ada-content-state'] == 'ready'
    assert states['shared']['data-ada-content-state'] == 'ready'
    assert states['plant_only']['data-ada-content-state'] == 'ready'
    assert all('data-ada-content-state-server-runtime' not in state for state in states.values())


def test_declared_construction_wraps_every_indicator() -> None:
    component = build_dashboard_global_indicators_runtime_component(
        _store(), binding=_binding(content_state=ContentState.CONSTRUCTION),
    )
    states = _states(component)
    assert len(states) == 3
    assert all(state['data-ada-content-state'] == 'construction' for state in states.values())
    assert all(state['data-ada-content-state-declared'] == 'construction'
               for state in states.values())


def test_integrated_operations_extension_owns_global_indicator_runtime_module() -> None:
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                'mine_component', 'Mine',
                subcomponents=(ToolSubcomponent('mine_card', 'Mine Card'),),
                scope=ToolScope.MINE,
            ),
            ToolComponent(
                'plant_component', 'Plant',
                subcomponents=(ToolSubcomponent('plant_card', 'Plant Card'),),
                scope=ToolScope.PLANT,
            ),
        ),
    )
    operational_binding = bind_operational_render(structure)
    extension = create_integrated_operations_extension(
        operational_binding, global_indicator_bindings=_binding().indicators,
    )
    assert tuple(module.name for module in extension.modules) == (
        'ada-integrated-operations-dashboard',
        'ada-integrated-operations-global-indicators',
    )


def test_global_indicator_runtime_is_mounted_from_product_catalog() -> None:
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                'mine_component', 'Mine',
                subcomponents=(ToolSubcomponent('mine_card', 'Mine Card'),),
                scope=ToolScope.MINE,
            ),
            ToolComponent(
                'plant_component', 'Plant',
                subcomponents=(ToolSubcomponent('plant_card', 'Plant Card'),),
                scope=ToolScope.PLANT,
            ),
        ),
    )
    extension = create_integrated_operations_extension(bind_operational_render(structure))
    assert tuple(module.name for module in extension.modules) == (
        'ada-integrated-operations-dashboard',
        'ada-integrated-operations-global-indicators',
    )


def test_unconfigured_tool_does_not_mount_global_indicator_runtime_or_fail_extension() -> None:
    extension = create_integrated_operations_extension(None)
    assert tuple(module.name for module in extension.modules) == (
        'ada-integrated-operations-dashboard',
    )


def test_global_indicators_wait_for_its_store_even_when_empty():
    from dash.exceptions import PreventUpdate

    dash_app = DashStub()
    create_dashboard_global_indicators_module(_binding()).register_callbacks(dash_app, object())
    with pytest.raises(PreventUpdate):
        dash_app.callback_function(None)
    _, _, ready = dash_app.callback_function({'latest': None, 'timeseries': None})
    assert ready == 'true'
