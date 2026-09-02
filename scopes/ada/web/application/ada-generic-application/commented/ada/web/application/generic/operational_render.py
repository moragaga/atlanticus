from __future__ import annotations

from collections.abc import Callable

from dash.development.base_component import Component

from ada.web.operational_render_binding import OperationalRenderBinding

# La aplicación concreta define cómo convierte el binding estructural en un body visual.
# El runtime genérico no conoce renderers, geometría, IDs DOM ni semántica del payload.
AdaOperationalBodyFactory = Callable[[OperationalRenderBinding], Component]


def validate_operational_render_application_binding(
    *,
    binding: OperationalRenderBinding | None,
    body_factory: AdaOperationalBodyFactory | None,
) -> None:
    # La frontera acepta únicamente el binding ya validado por Operational Render Binding.
    if binding is not None and not isinstance(binding, OperationalRenderBinding):
        raise TypeError('Operational render binding must be an OperationalRenderBinding value')
    if body_factory is not None and not callable(body_factory):
        raise TypeError('Operational body factory must be callable')
    # Un binding no puede materializarse sin una decisión visual explícita de la aplicación.
    if binding is not None and body_factory is None:
        raise ValueError('Operational render binding requires an operational body factory')


def build_operational_body(
    *,
    binding: OperationalRenderBinding | None,
    body_factory: AdaOperationalBodyFactory | None,
) -> Component | None:
    validate_operational_render_application_binding(
        binding=binding,
        body_factory=body_factory,
    )
    if binding is None:
        return None
    # El factory recibe el binding intacto. Allí la aplicación puede mapear component_key a
    # renderers concretos sin introducir una DSL o un registry en Atlanticus.
    body = body_factory(binding)
    if not isinstance(body, Component):
        raise TypeError('Operational body factory must return a Dash Component')
    return body
