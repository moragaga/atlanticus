# Adaptador de presentación de Latest para componentes operacionales de Generic. La validación del
# envelope status/value_kind/value ya no vive aquí: Generic solo convierte el resultado semántico
# del decoder compartido a la representación visual que necesita esta superficie.

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from dash import Input, Output, html
from dash.development.base_component import Component

from ada.web.kpis.collector import (
    DecodedKpiLatestValue,
    KpiLatestValueState,
    component_kpi_store_id,
    decode_kpi_latest_value,
)
from ada.web.operational_render_binding import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)
from ada.web.ui.display_status import DisplayStatus, build_display_status_icon
from atlanticus.web.modules import WebModule

OPERATIONAL_LATEST_HOST_TYPE = 'ada-operational-latest-host'


@dataclass(frozen=True, slots=True)
class OperationalLatestPresentation:
    tool_key: str
    component_key: str
    store_data: object

    def __post_init__(self) -> None:
        address = component_kpi_store_id(self.tool_key, self.component_key)
        object.__setattr__(self, 'tool_key', address['tool'])
        object.__setattr__(self, 'component_key', address['component'])

    def resolve(self, kpi_key: str) -> object:
        return resolve_operational_latest_value(
            self.store_data,
            tool_key=self.tool_key,
            component_key=self.component_key,
            kpi_key=kpi_key,
        )

    def resolve_many(self, kpi_keys: Iterable[str]) -> dict[str, object]:
        if isinstance(kpi_keys, str | bytes):
            raise TypeError('kpi_keys must be an iterable of KPI keys')
        return {kpi_key: self.resolve(kpi_key) for kpi_key in kpi_keys}

    def __getitem__(self, kpi_key: str) -> object:
        return self.resolve(kpi_key)


AdaOperationalLatestRenderer = Callable[
    [OperationalRenderBinding, OperationalComponentBinding, OperationalLatestPresentation],
    Component,
]


def operational_latest_host_id(tool_key: str, component_key: str) -> dict[str, str]:
    address = component_kpi_store_id(tool_key, component_key)
    return {
        'type': OPERATIONAL_LATEST_HOST_TYPE,
        'tool': address['tool'],
        'component': address['component'],
    }


def materialize_operational_latest_hosts(
    binding: OperationalRenderBinding,
) -> tuple[Component, ...]:
    if not isinstance(binding, OperationalRenderBinding):
        raise TypeError('Operational latest hosts require OperationalRenderBinding')
    return tuple(
        html.Div(
            id=operational_latest_host_id(
                binding.structure.tool_key,
                component_binding.component.key,
            ),
            **{'data-ada-component-key': component_binding.component.key},
        )
        for component_binding in binding.components
    )


def build_operational_latest_body(binding: OperationalRenderBinding) -> Component:
    return html.Div(
        materialize_operational_latest_hosts(binding),
        id='ada-operational-body',
    )


def create_operational_latest_render_module(
    binding: OperationalRenderBinding,
    *,
    renderers: Mapping[str, AdaOperationalLatestRenderer],
) -> WebModule:
    _validate_renderers(binding, renderers)

    def register_callbacks(dash_app, _services) -> None:
        for component_binding in binding.components:
            _register_component_callback(
                dash_app,
                binding=binding,
                component_binding=component_binding,
                renderer=renderers[component_binding.component.key],
            )

    return WebModule(
        name='ada-operational-latest-render',
        register_callbacks=register_callbacks,
    )


# La identidad y estructura del Component Store siguen siendo responsabilidad de Generic. Una vez
# localizado el KPI, el envelope se delega al decoder canónico del Collector.
def resolve_operational_latest_value(
    store_data: object,
    *,
    tool_key: str,
    component_key: str,
    kpi_key: str,
) -> object:
    expected = component_kpi_store_id(tool_key, component_key)
    resolved_kpi_key = _required_text(kpi_key, 'kpi_key')

    if store_data is None:
        return _status_icon(DisplayStatus.EMPTY)
    if not isinstance(store_data, Mapping):
        return _status_icon(DisplayStatus.INVALID)
    if store_data.get('tool_key') != expected['tool']:
        return _status_icon(DisplayStatus.INVALID)
    if store_data.get('component_key') != expected['component']:
        return _status_icon(DisplayStatus.INVALID)
    if 'latest' not in store_data:
        return _status_icon(DisplayStatus.INVALID)

    latest = store_data['latest']
    if latest is None:
        return _status_icon(DisplayStatus.EMPTY)
    if not isinstance(latest, Mapping) or set(latest) != {'manifest', 'values'}:
        return _status_icon(DisplayStatus.INVALID)
    if not isinstance(latest['manifest'], Mapping):
        return _status_icon(DisplayStatus.INVALID)

    values = latest['values']
    if not isinstance(values, Mapping):
        return _status_icon(DisplayStatus.INVALID)
    present = resolved_kpi_key in values
    decoded = decode_kpi_latest_value(values.get(resolved_kpi_key), present=present)
    return _present_decoded_value(decoded)


# Solo esta capa decide que MISSING se dibuja como EMPTY y que ERROR/INVALID/NOT_MAPPED usan sus
# iconos correspondientes. Otros consumidores, como Time Status, podrán tomar decisiones distintas.
def _present_decoded_value(value: DecodedKpiLatestValue) -> object:
    if value.state is KpiLatestValueState.OK:
        return value.value
    statuses = {
        KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
        KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
        KpiLatestValueState.INVALID: DisplayStatus.INVALID,
        KpiLatestValueState.ERROR: DisplayStatus.ERROR,
    }
    return _status_icon(statuses[value.state])


def _status_icon(status: DisplayStatus) -> Component:
    icon = build_display_status_icon(status)
    if icon is None:
        raise RuntimeError('Degraded operational KPI presentation requires a status icon')
    return icon


def _register_component_callback(
    dash_app,
    *,
    binding: OperationalRenderBinding,
    component_binding: OperationalComponentBinding,
    renderer: AdaOperationalLatestRenderer,
) -> None:
    tool_key = binding.structure.tool_key
    component_key = component_binding.component.key

    @dash_app.callback(
        Output(operational_latest_host_id(tool_key, component_key), 'children'),
        Input(component_kpi_store_id(tool_key, component_key), 'data'),
    )
    def render_component(store_data: object):
        presentation = OperationalLatestPresentation(
            tool_key=tool_key,
            component_key=component_key,
            store_data=store_data,
        )
        rendered = renderer(binding, component_binding, presentation)
        if not isinstance(rendered, Component):
            raise TypeError(
                f'Operational latest renderer must return a Dash Component: {component_key!r}'
            )
        return rendered


def _validate_renderers(
    binding: OperationalRenderBinding,
    renderers: Mapping[str, AdaOperationalLatestRenderer],
) -> None:
    if not isinstance(binding, OperationalRenderBinding):
        raise TypeError('Operational latest rendering requires OperationalRenderBinding')
    if not isinstance(renderers, Mapping):
        raise TypeError('Operational latest renderers must be a mapping')

    expected_keys = binding.component_keys
    expected_key_set = set(expected_keys)
    for component_key, renderer in renderers.items():
        if not isinstance(component_key, str):
            raise TypeError('Operational latest renderer key must be a string')
        if component_key not in expected_key_set:
            raise ValueError(f'Unknown operational latest renderer: {component_key!r}')
        if not callable(renderer):
            raise TypeError(f'Operational latest renderer must be callable: {component_key!r}')

    missing_key = next((key for key in expected_keys if key not in renderers), None)
    if missing_key is not None:
        raise ValueError(f'Missing operational latest renderer: {missing_key!r}')


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field_name} must be a non-empty trimmed string')
    return value
