# Espejo pedagógico: normaliza Store.latest antes de entregarlo a modeladores y builders.
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from dash import Input, Output, html
from dash.development.base_component import Component

from ada.web.kpis.collector import component_kpi_store_id
from ada.web.operational_render_binding import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)
from ada.web.ui.display_status import DisplayStatus, build_display_status_icon
from atlanticus.web.modules import WebModule

OPERATIONAL_LATEST_HOST_TYPE = 'ada-operational-latest-host'

# Encapsula el Store ya serializado y expone valores listos para consumo de presentación.
@dataclass(frozen=True, slots=True)
class OperationalLatestPresentation:
    tool_key: str
    component_key: str
    store_data: object

    def __post_init__(self) -> None:
        address = component_kpi_store_id(self.tool_key, self.component_key)
        object.__setattr__(self, 'tool_key', address['tool'])
        object.__setattr__(self, 'component_key', address['component'])

    # Devuelve directamente valor, JSON estructural o componente Dash de estado.
    def resolve(self, kpi_key: str) -> object:
        return resolve_operational_latest_value(
            self.store_data,
            tool_key=self.tool_key,
            component_key=self.component_key,
            kpi_key=kpi_key,
        )

    # Permite normalizar de una vez el conjunto de claves que consumirá un modelador.
    def resolve_many(self, kpi_keys: Iterable[str]) -> dict[str, object]:
        if isinstance(kpi_keys, str | bytes):
            raise TypeError('kpi_keys must be an iterable of KPI keys')
        return {kpi_key: self.resolve(kpi_key) for kpi_key in kpi_keys}

    # Hace posible usar presentation['kpi'] sin repetir lógica de status/value_kind aguas abajo.
    def __getitem__(self, kpi_key: str) -> object:
        return self.resolve(kpi_key)


AdaOperationalLatestRenderer = Callable[
    [OperationalRenderBinding, OperationalComponentBinding, OperationalLatestPresentation],
    Component,
]


# El host comparte dirección Tool/Component con el Store, pero conserva identidad Dash propia.
def operational_latest_host_id(tool_key: str, component_key: str) -> dict[str, str]:
    address = component_kpi_store_id(tool_key, component_key)
    return {
        'type': OPERATIONAL_LATEST_HOST_TYPE,
        'tool': address['tool'],
        'component': address['component'],
    }


# Materializa un host por componente según el orden de Tool Structure.
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


# Construye el cuerpo donde los callbacks depositarán la UI concreta.
def build_operational_latest_body(binding: OperationalRenderBinding) -> Component:
    return html.Div(
        materialize_operational_latest_hosts(binding),
        id='ada-operational-body',
    )


# Registra el enlace reactivo Store.data -> host.children por componente.
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


# Valida el contrato Store.latest una sola vez y entrega el objeto final de presentación.
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
    if resolved_kpi_key not in values:
        return _status_icon(DisplayStatus.NOT_MAPPED)

    entry = values[resolved_kpi_key]
    if not isinstance(entry, Mapping) or set(entry) != {'status', 'value_kind', 'value'}:
        return _status_icon(DisplayStatus.INVALID)
    return _resolve_delivery_entry(entry)


# JSON estructural siempre conserva su forma; VALUE degradado se convierte en icono compartido.
def _resolve_delivery_entry(entry: Mapping[str, object]) -> object:
    status = entry['status']
    value_kind = entry['value_kind']
    payload = entry['value']

    if value_kind == 'json':
        if isinstance(payload, list | dict) and status in {'ok', 'missing', 'error'}:
            return payload
        if payload is not None:
            return _status_icon(DisplayStatus.INVALID)
        if status == 'missing':
            return _status_icon(DisplayStatus.EMPTY)
        if status == 'error':
            return _status_icon(DisplayStatus.ERROR)
        return _status_icon(DisplayStatus.INVALID)

    if value_kind == 'value':
        if status == 'ok' and payload is not None:
            return payload
        if payload is not None:
            return _status_icon(DisplayStatus.INVALID)
        if status == 'missing':
            return _status_icon(DisplayStatus.EMPTY)
        if status == 'error':
            return _status_icon(DisplayStatus.ERROR)
        return _status_icon(DisplayStatus.INVALID)

    if value_kind is None and status == 'missing' and payload is None:
        return _status_icon(DisplayStatus.EMPTY)
    return _status_icon(DisplayStatus.INVALID)


# Centraliza la construcción de iconos para que los consumidores no inspeccionen estados.
def _status_icon(status: DisplayStatus) -> Component:
    icon = build_display_status_icon(status)
    if icon is None:
        raise RuntimeError('Degraded operational KPI presentation requires a status icon')
    return icon


# Conserva exactamente la dirección Tool/Component entre Input y Output.
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


# Mantiene el contrato de un renderer por componente estructural.
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


# KPI key sigue siendo la identidad externa del modelador.
def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field_name} must be a non-empty trimmed string')
    return value
