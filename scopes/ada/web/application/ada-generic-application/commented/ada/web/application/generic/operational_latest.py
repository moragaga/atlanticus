# Espejo pedagógico: la frontera Store -> Dash conserva datos serializables hasta el callback.
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from dash import Input, Output, html
from dash.development.base_component import Component

from ada.web.kpis.collector import component_kpi_store_id
from ada.web.operational_render_binding import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)
from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    build_display_status_icon,
)
from atlanticus.web.modules import WebModule

OPERATIONAL_LATEST_HOST_TYPE = 'ada-operational-latest-host'

AdaOperationalKpiValueFactory = Callable[[object], Component]


# Encapsula el JSON recibido desde dcc.Store y resuelve estados visuales por KPI.
@dataclass(frozen=True, slots=True)
class OperationalLatestPresentation:
    tool_key: str
    component_key: str
    store_data: object

    def __post_init__(self) -> None:
        address = component_kpi_store_id(self.tool_key, self.component_key)
        object.__setattr__(self, 'tool_key', address['tool'])
        object.__setattr__(self, 'component_key', address['component'])

    def resolve(self, kpi_key: str) -> DisplayValue:
        return resolve_operational_latest_display_value(
            self.store_data,
            tool_key=self.tool_key,
            component_key=self.component_key,
            kpi_key=kpi_key,
        )

    def render(
        self,
        kpi_key: str,
        value_factory: AdaOperationalKpiValueFactory,
        *,
        status_class_name: str | None = None,
    ) -> Component:
        return build_operational_latest_kpi(
            self,
            kpi_key=kpi_key,
            value_factory=value_factory,
            status_class_name=status_class_name,
        )


AdaOperationalLatestRenderer = Callable[
    [OperationalRenderBinding, OperationalComponentBinding, OperationalLatestPresentation],
    Component,
]


# Usa la misma identidad tool/component del Store, con un tipo distinto para el host de salida.
def operational_latest_host_id(tool_key: str, component_key: str) -> dict[str, str]:
    address = component_kpi_store_id(tool_key, component_key)
    return {
        'type': OPERATIONAL_LATEST_HOST_TYPE,
        'tool': address['tool'],
        'component': address['component'],
    }


# Materializa un host Dash por componente, respetando el orden de Tool Structure.
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


# Construye el cuerpo operacional mínimo donde los callbacks depositan la UI concreta.
def build_operational_latest_body(binding: OperationalRenderBinding) -> Component:
    return html.Div(
        materialize_operational_latest_hosts(binding),
        id='ada-operational-body',
    )


# Registra un callback Store.data -> host.children por cada componente configurado.
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


# Valida sólo Delivery.latest y lo traduce a DisplayStatus compartido por ADA UI.
def resolve_operational_latest_display_value(
    store_data: object,
    *,
    tool_key: str,
    component_key: str,
    kpi_key: str,
) -> DisplayValue:
    expected = component_kpi_store_id(tool_key, component_key)
    resolved_kpi_key = _required_text(kpi_key, 'kpi_key')

    if store_data is None:
        return DisplayValue.empty()
    if not isinstance(store_data, Mapping):
        return DisplayValue.invalid()
    if store_data.get('tool_key') != expected['tool']:
        return DisplayValue.invalid()
    if store_data.get('component_key') != expected['component']:
        return DisplayValue.invalid()
    if 'latest' not in store_data:
        return DisplayValue.invalid()

    latest = store_data['latest']
    if latest is None:
        return DisplayValue.empty()
    if not isinstance(latest, Mapping) or set(latest) != {'manifest', 'values'}:
        return DisplayValue.invalid()
    if not isinstance(latest['manifest'], Mapping):
        return DisplayValue.invalid()

    values = latest['values']
    if not isinstance(values, Mapping):
        return DisplayValue.invalid()
    if resolved_kpi_key not in values:
        return DisplayValue.not_mapped()

    value = values[resolved_kpi_key]
    if not isinstance(value, Mapping) or set(value) != {'status', 'value_kind', 'value'}:
        return DisplayValue.invalid()
    return _resolve_delivery_value(value)


# Crea componentes Dash sólo después del Store: valor normal o icono degradado compartido.
def build_operational_latest_kpi(
    presentation: OperationalLatestPresentation,
    *,
    kpi_key: str,
    value_factory: AdaOperationalKpiValueFactory,
    status_class_name: str | None = None,
) -> Component:
    if not isinstance(presentation, OperationalLatestPresentation):
        raise TypeError('presentation must be OperationalLatestPresentation')
    if not callable(value_factory):
        raise TypeError('value_factory must be callable')

    display = presentation.resolve(kpi_key)
    if display.status is DisplayStatus.OK:
        value = display.value
        if value is None:
            raise RuntimeError('OK operational KPI presentation has no value')
        rendered = value_factory(value)
        if not isinstance(rendered, Component):
            raise TypeError('Operational KPI value factory must return a Dash Component')
        return rendered

    icon = build_display_status_icon(
        display.status,
        class_name=status_class_name,
    )
    if icon is None:
        raise RuntimeError('Degraded operational KPI presentation requires a status icon')
    return icon


# Cada callback conserva exactamente la dirección tool/component entre Input y Output.
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


# Exige un renderer explícito por cada componente estructural y rechaza extras.
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


# Traduce los estados del contrato Delivery: ok, missing y error.
def _resolve_delivery_value(value: Mapping[str, object]) -> DisplayValue:
    status = value['status']
    value_kind = value['value_kind']
    payload = value['value']

    if status == 'ok':
        if not _optional_value_kind_is_valid(value_kind) or value_kind is None or payload is None:
            return DisplayValue.invalid()
        return DisplayValue.ok(payload)

    if status == 'missing':
        if value_kind is not None or payload is not None:
            return DisplayValue.invalid()
        return DisplayValue.empty()

    if status == 'error':
        if payload is not None or not _optional_value_kind_is_valid(value_kind):
            return DisplayValue.invalid()
        return DisplayValue.error()

    return DisplayValue.invalid()


# No inventa un catálogo de tipos nuevo; sólo valida el contrato textual de value_kind.
def _optional_value_kind_is_valid(value: object) -> bool:
    return value is None or (isinstance(value, str) and bool(value) and value == value.strip())


# Los KPI keys pueden tener convención propia; aquí sólo se exige texto limpio no vacío.
def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field_name} must be a non-empty trimmed string')
    return value
