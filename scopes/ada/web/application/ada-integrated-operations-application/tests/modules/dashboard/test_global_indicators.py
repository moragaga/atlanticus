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
    resolve_dashboard_global_indicators_runtime_state,
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
            DashboardGlobalIndicatorBinding(_definition('mine_only'), (ToolScope.MINE,)),
            DashboardGlobalIndicatorBinding(
                _definition('shared'),
                (ToolScope.MINE, ToolScope.PLANT),
            ),
            DashboardGlobalIndicatorBinding(_definition('plant_only'), (ToolScope.PLANT,)),
        ),
        content_state=content_state,
    )


def _ok(value: object) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'value', 'value': value}


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


def test_binding_supports_shared_indicator_and_collection_level_content_state() -> None:
    binding = _binding()

    assert binding.content_state is ContentState.READY
    assert binding.indicators[1].appears_in(ToolScope.MINE)
    assert binding.indicators[1].appears_in(ToolScope.PLANT)
    assert tuple(item.definition.key for item in binding.indicators) == (
        'mine_only',
        'shared',
        'plant_only',
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
            'integrated_operations',
            (shared,),
            content_state='construction',
        )


def test_resolver_maps_canonical_latest_envelopes_and_preserves_kpi_inspection_keys() -> None:
    resolved = resolve_dashboard_global_indicators(_store(), binding=_binding())
    shared = resolved[1].state

    assert shared.key == 'shared'
    assert shared.measurements[0].actual_value.status is DisplayStatus.OK
    assert shared.measurements[0].actual_value.value == 10
    assert shared.measurements[0].actual_kpi_key == 'shared.turno.actual'
    assert shared.measurements[0].color_class == 'indicator-positive'
    assert shared.last_measurement is not None
    assert shared.last_measurement.actual_kpi_key == 'shared.latest'


def test_runtime_state_requires_every_kpi_declared_by_the_collection() -> None:
    binding = _binding()
    store = _store()

    assert (
        resolve_dashboard_global_indicators_runtime_state(store, binding=binding)
        is ContentState.READY
    )

    del store['latest']['values']['shared.dia.plan']

    assert (
        resolve_dashboard_global_indicators_runtime_state(store, binding=binding)
        is ContentState.SOURCE_ERROR
    )


def test_runtime_state_rejects_missing_or_invalid_latest_payload() -> None:
    binding = _binding()
    assert (
        resolve_dashboard_global_indicators_runtime_state(None, binding=binding)
        is ContentState.SOURCE_ERROR
    )

    store = _store()
    store['latest']['values']['shared.turno.actual'] = {
        'status': 'ok',
        'value_kind': 'json',
        'value': {'value': 10},
    }

    assert (
        resolve_dashboard_global_indicators_runtime_state(store, binding=binding)
        is ContentState.SOURCE_ERROR
    )


def test_runtime_renders_each_indicator_once_and_shared_scope_metadata_once() -> None:
    component = build_dashboard_global_indicators_runtime_component(_store(), binding=_binding())
    placements = [
        node for node in _walk(component) if _props(node).get('data-ada-io-global-indicator-key')
    ]

    assert len(placements) == 3
    shared = next(
        node for node in placements if _props(node)['data-ada-io-global-indicator-key'] == 'shared'
    )
    assert _props(shared)['data-ada-io-global-indicator-scopes'] == 'mine,plant'
    assert _props(shared)['data-ada-io-scope-mine'] == 'true'
    assert _props(shared)['data-ada-io-scope-plant'] == 'true'


def test_runtime_callback_bridges_exact_system_store_to_header_slot() -> None:
    binding = _binding()
    module = create_dashboard_global_indicators_module(binding)
    dash_app = DashStub()
    module.register_callbacks(dash_app, object())

    component, empty = dash_app.callback_function(_store())
    grids = [
        node
        for node in _walk(component)
        if _props(node).get('data-ada-io-global-indicators-runtime') == 'true'
    ]

    assert module.name == 'ada-integrated-operations-global-indicators'
    assert module.asset_layers == ()
    assert empty == 'false'
    assert len(grids) == 1
    assert _props(component)['data-ada-content-state'] == 'ready'
    assert _props(component)['data-ada-content-state-operational'] == 'true'
    assert system_kpi_store_id('integrated_operations', GLOBAL_INDICATORS_DESTINATION_KEY) == {
        'type': 'ada-kpi-system-store',
        'tool': 'integrated_operations',
        'destination': 'global_indicators',
    }
    outputs = dash_app.callback_args[:2]
    assert all(output.component_id == GLOBAL_INDICATORS_SLOT_ID for output in outputs)


def test_runtime_callback_degrades_complete_collection_from_empty_system_store() -> None:
    binding = _binding()
    module = create_dashboard_global_indicators_module(binding)
    dash_app = DashStub()
    module.register_callbacks(dash_app, object())

    component, empty = dash_app.callback_function(
        {
            'tool_key': 'integrated_operations',
            'destination_key': 'global_indicators',
            'latest': None,
            'timeseries': None,
        }
    )
    placements = [
        node for node in _walk(component) if _props(node).get('data-ada-io-global-indicator-key')
    ]

    assert empty == 'false'
    assert len(placements) == 3
    assert _props(component)['data-ada-content-state'] == 'source_error'
    assert _props(component)['data-ada-content-state-declared'] == 'ready'
    assert _props(component)['data-ada-content-state-operational'] == 'true'


def test_declared_construction_wraps_the_complete_collection() -> None:
    component = build_dashboard_global_indicators_runtime_component(
        _store(),
        binding=_binding(content_state=ContentState.CONSTRUCTION),
    )

    assert _props(component)['data-ada-content-state'] == 'construction'
    assert _props(component)['data-ada-content-state-declared'] == 'construction'
    assert _props(component)['data-ada-content-state-operational'] == 'true'
    placements = [
        node for node in _walk(component) if _props(node).get('data-ada-io-global-indicator-key')
    ]
    assert len(placements) == 3


def test_integrated_operations_extension_owns_global_indicator_runtime_module() -> None:
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                'mine_component',
                'Mine',
                subcomponents=(ToolSubcomponent('mine_card', 'Mine Card'),),
                scope=ToolScope.MINE,
            ),
            ToolComponent(
                'plant_component',
                'Plant',
                subcomponents=(ToolSubcomponent('plant_card', 'Plant Card'),),
                scope=ToolScope.PLANT,
            ),
        ),
    )
    operational_binding = bind_operational_render(structure)

    extension = create_integrated_operations_extension(
        operational_binding,
        global_indicator_bindings=_binding().indicators,
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
                'mine_component',
                'Mine',
                subcomponents=(ToolSubcomponent('mine_card', 'Mine Card'),),
                scope=ToolScope.MINE,
            ),
            ToolComponent(
                'plant_component',
                'Plant',
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
