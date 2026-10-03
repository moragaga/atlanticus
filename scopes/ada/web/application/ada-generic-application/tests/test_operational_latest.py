from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.application.generic.operational_latest import (
    OPERATIONAL_LATEST_HOST_TYPE,
    OperationalLatestPresentation,
    build_operational_latest_body,
    create_operational_latest_render_module,
    operational_latest_host_id,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.operational_render_binding import bind_operational_render
from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from atlanticus.web.services import ServiceRegistry


class DashStub:
    def __init__(self) -> None:
        self.callback_args = []
        self.callback_functions = []

    def callback(self, *args, **_kwargs):
        self.callback_args.append(args)

        def register(function):
            self.callback_functions.append(function)
            return function

        return register


def _binding():
    return bind_operational_render(
        ToolStructure(
            tool_key='integrated_operations',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                ToolComponent(
                    key='mine',
                    display_name='Mina',
                    scope=ToolScope.MINE,
                    subcomponents=(ToolSubcomponent(key='mine_phase', display_name='Fase Mina'),),
                ),
                ToolComponent(
                    key='plant',
                    display_name='Planta',
                    scope=ToolScope.PLANT,
                    subcomponents=(ToolSubcomponent(key='plant_phase', display_name='Fase Planta'),),
                ),
            ),
        )
    )


def _store(*, values=None, component_key='mine', latest=..., timeseries=None):
    resolved_latest = (
        {
            'manifest': {'revision': 'latest-r1'},
            'values': values if values is not None else {
                'crusher_rate': {'status': 'ok', 'value_kind': 'value', 'value': '42,0'}
            },
        }
        if latest is ...
        else latest
    )
    return {
        'tool_key': 'integrated_operations',
        'component_key': component_key,
        'latest': resolved_latest,
        'timeseries': timeseries,
    }


def _prop(component, name: str):
    return component.to_plotly_json()['props'][name]


def test_body_materializes_one_output_host_per_tool_component() -> None:
    binding = _binding()
    body = build_operational_latest_body(binding)
    assert body.id == 'ada-operational-body'
    assert tuple(child.id for child in body.children) == (
        operational_latest_host_id('integrated_operations', 'mine'),
        operational_latest_host_id('integrated_operations', 'plant'),
    )
    assert body.children[0].id['type'] == OPERATIONAL_LATEST_HOST_TYPE


def test_render_module_binds_matching_store_and_exposes_ready_presentation() -> None:
    binding = _binding()

    def renderer(_binding, _component_binding, presentation):
        return html.P(presentation['crusher_rate'])

    module = create_operational_latest_render_module(
        binding,
        renderers={'mine': renderer, 'plant': renderer},
    )
    dash_app = DashStub()
    module.register_callbacks(dash_app, ServiceRegistry())

    first_output, first_input = dash_app.callback_args[0]
    assert first_output.component_id == operational_latest_host_id('integrated_operations', 'mine')
    assert first_input.component_id == component_kpi_store_id('integrated_operations', 'mine')
    rendered = dash_app.callback_functions[0](_store())
    assert rendered.children == '42,0'


def test_value_ok_is_returned_directly_without_consumer_inference() -> None:
    presentation = OperationalLatestPresentation('integrated_operations', 'mine', _store())
    assert presentation['crusher_rate'] == '42,0'
    assert presentation.resolve_many(('crusher_rate',)) == {'crusher_rate': '42,0'}


def test_value_missing_and_error_are_returned_as_status_components() -> None:
    missing = OperationalLatestPresentation(
        'integrated_operations',
        'mine',
        _store(values={'kpi': {'status': 'missing', 'value_kind': None, 'value': None}}),
    )['kpi']
    error = OperationalLatestPresentation(
        'integrated_operations',
        'mine',
        _store(values={'kpi': {'status': 'error', 'value_kind': 'value', 'value': None}}),
    )['kpi']
    assert isinstance(missing, Component)
    assert isinstance(error, Component)
    assert _prop(missing, 'src').endswith('/img/status/empty-data.svg')
    assert _prop(error, 'src').endswith('/img/status/internal-error.svg')


def test_json_ok_missing_and_error_all_preserve_structural_payload() -> None:
    for status in ('ok', 'missing', 'error'):
        payload = {'rows': [], 'columns': ['name', 'value']}
        presentation = OperationalLatestPresentation(
            'integrated_operations',
            'mine',
            _store(values={'table': {'status': status, 'value_kind': 'json', 'value': payload}}),
        )
        assert presentation['table'] == payload


def test_json_degraded_without_structural_payload_falls_back_to_status_icon() -> None:
    presentation = OperationalLatestPresentation(
        'integrated_operations',
        'mine',
        _store(values={'table': {'status': 'missing', 'value_kind': 'json', 'value': None}}),
    )
    resolved = presentation['table']
    assert isinstance(resolved, Component)
    assert _prop(resolved, 'src').endswith('/img/status/empty-data.svg')


def test_absent_key_and_invalid_payload_are_normalized_to_icons() -> None:
    absent = OperationalLatestPresentation(
        'integrated_operations', 'mine', _store(values={})
    )['unknown']
    invalid = OperationalLatestPresentation(
        'integrated_operations',
        'mine',
        _store(values={'kpi': {'status': 'ok', 'value_kind': 'value', 'value': None}}),
    )['kpi']
    assert _prop(absent, 'src').endswith('/img/status/not-mapped.svg')
    assert _prop(invalid, 'src').endswith('/img/status/invalid-data.svg')


def test_timeseries_remains_outside_latest_normalization() -> None:
    presentation = OperationalLatestPresentation(
        'integrated_operations',
        'mine',
        _store(timeseries={'malformed': object()}),
    )
    assert presentation['crusher_rate'] == '42,0'


def test_store_identity_mismatch_is_invalid() -> None:
    presentation = OperationalLatestPresentation(
        'integrated_operations',
        'mine',
        _store(component_key='plant'),
    )
    resolved = presentation['crusher_rate']
    assert _prop(resolved, 'src').endswith('/img/status/invalid-data.svg')


def test_render_module_requires_renderer_for_every_component() -> None:
    try:
        create_operational_latest_render_module(
            _binding(),
            renderers={'mine': lambda *_args: html.Div()},
        )
    except ValueError as error:
        assert str(error) == "Missing operational latest renderer: 'plant'"
    else:
        raise AssertionError('Expected missing renderer to fail')
