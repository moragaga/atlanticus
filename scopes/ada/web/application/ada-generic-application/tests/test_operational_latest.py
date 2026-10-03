from __future__ import annotations

from dash import html

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
from ada.web.ui.display_status import DisplayStatus
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
                    subcomponents=(
                        ToolSubcomponent(key='plant_phase', display_name='Fase Planta'),
                    ),
                ),
            ),
        )
    )


def _store(
    *,
    component_key: str = 'mine',
    values: dict[str, object] | None = None,
    latest: object = ...,
    timeseries: object = None,
):
    resolved_latest = (
        {
            'manifest': {'revision': 'latest-r1'},
            'values': (
                values
                if values is not None
                else {
                    'crusher_rate': {
                        'status': 'ok',
                        'value_kind': 'float',
                        'value': 42.0,
                    }
                }
            ),
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


def test_render_module_binds_each_host_to_the_matching_component_store() -> None:
    binding = _binding()
    observed = []

    def renderer(_binding, component_binding, presentation):
        observed.append((component_binding.component.key, presentation))
        return html.Div(component_binding.component.display_name)

    module = create_operational_latest_render_module(
        binding,
        renderers={
            'mine': renderer,
            'plant': renderer,
        },
    )
    dash_app = DashStub()

    module.register_callbacks(dash_app, ServiceRegistry())

    assert len(dash_app.callback_args) == 2
    first_output, first_input = dash_app.callback_args[0]
    assert first_output.component_id == operational_latest_host_id(
        'integrated_operations',
        'mine',
    )
    assert first_output.component_property == 'children'
    assert first_input.component_id == component_kpi_store_id(
        'integrated_operations',
        'mine',
    )
    assert first_input.component_property == 'data'

    rendered = dash_app.callback_functions[0](_store())

    assert rendered.children == 'Mina'
    assert observed[0][0] == 'mine'
    assert isinstance(observed[0][1], OperationalLatestPresentation)


def test_ok_delivery_value_builds_dash_only_after_store_boundary() -> None:
    presentation = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(),
    )

    display = presentation.resolve('crusher_rate')
    rendered = presentation.render(
        'crusher_rate',
        lambda value: html.Span(f'{value:.1f}', id='crusher-rate'),
    )

    assert display.status is DisplayStatus.OK
    assert display.value == 42.0
    assert rendered.id == 'crusher-rate'
    assert rendered.children == '42.0'


def test_missing_delivery_value_uses_shared_empty_icon() -> None:
    presentation = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(
            values={
                'crusher_rate': {
                    'status': 'missing',
                    'value_kind': None,
                    'value': None,
                }
            }
        ),
    )

    display = presentation.resolve('crusher_rate')
    rendered = presentation.render('crusher_rate', lambda value: html.Span(value))

    assert display.status is DisplayStatus.EMPTY
    assert _prop(rendered, 'src').endswith('/img/status/empty-data.svg')


def test_error_delivery_value_uses_shared_internal_error_icon() -> None:
    presentation = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(
            values={
                'crusher_rate': {
                    'status': 'error',
                    'value_kind': 'float',
                    'value': None,
                }
            }
        ),
    )

    assert presentation.resolve('crusher_rate').status is DisplayStatus.ERROR
    rendered = presentation.render('crusher_rate', lambda value: html.Span(value))

    assert _prop(rendered, 'src').endswith('/img/status/internal-error.svg')


def test_absent_expected_kpi_uses_shared_not_mapped_icon() -> None:
    presentation = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(values={}),
    )

    assert presentation.resolve('crusher_rate').status is DisplayStatus.NOT_MAPPED
    rendered = presentation.render('crusher_rate', lambda value: html.Span(value))

    assert _prop(rendered, 'src').endswith('/img/status/not-mapped.svg')


def test_invalid_browser_payload_uses_shared_invalid_icon() -> None:
    presentation = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(
            values={
                'crusher_rate': {
                    'status': 'ok',
                    'value_kind': 'float',
                    'value': None,
                }
            }
        ),
    )

    assert presentation.resolve('crusher_rate').status is DisplayStatus.INVALID
    rendered = presentation.render('crusher_rate', lambda value: html.Span(value))

    assert _prop(rendered, 'src').endswith('/img/status/invalid-data.svg')


def test_latest_absence_is_empty_and_timeseries_is_ignored() -> None:
    without_latest = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(latest=None, timeseries={'any': 'future-contract'}),
    )
    with_latest_and_timeseries = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(timeseries={'malformed': object()}),
    )

    assert without_latest.resolve('crusher_rate').status is DisplayStatus.EMPTY
    assert with_latest_and_timeseries.resolve('crusher_rate').status is DisplayStatus.OK


def test_store_identity_mismatch_is_invalid() -> None:
    presentation = OperationalLatestPresentation(
        tool_key='integrated_operations',
        component_key='mine',
        store_data=_store(component_key='plant'),
    )

    assert presentation.resolve('crusher_rate').status is DisplayStatus.INVALID


def test_render_module_requires_one_renderer_per_component() -> None:
    binding = _binding()

    try:
        create_operational_latest_render_module(
            binding,
            renderers={'mine': lambda *_args: html.Div()},
        )
    except ValueError as error:
        assert str(error) == "Missing operational latest renderer: 'plant'"
    else:
        raise AssertionError('Expected missing renderer to fail')
