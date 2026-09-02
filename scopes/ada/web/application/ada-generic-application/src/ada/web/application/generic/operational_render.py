from __future__ import annotations

from collections.abc import Callable

from dash.development.base_component import Component

from ada.web.operational_render_binding import OperationalRenderBinding

AdaOperationalBodyFactory = Callable[[OperationalRenderBinding], Component]


def validate_operational_render_application_binding(
    *,
    binding: OperationalRenderBinding | None,
    body_factory: AdaOperationalBodyFactory | None,
) -> None:
    if binding is not None and not isinstance(binding, OperationalRenderBinding):
        raise TypeError('Operational render binding must be an OperationalRenderBinding value')
    if body_factory is not None and not callable(body_factory):
        raise TypeError('Operational body factory must be callable')
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
    body = body_factory(binding)
    if not isinstance(body, Component):
        raise TypeError('Operational body factory must return a Dash Component')
    return body
