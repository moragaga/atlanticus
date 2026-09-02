from __future__ import annotations

from collections.abc import Callable, Mapping

from dash.development.base_component import Component

from ada.web.operational_render_binding import (
    OperationalComponentBinding,
    OperationalRenderBinding,
)

AdaOperationalBodyFactory = Callable[[OperationalRenderBinding], Component]
AdaOperationalComponentRenderer = Callable[
    [OperationalRenderBinding, OperationalComponentBinding],
    Component,
]


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


def materialize_operational_components(
    binding: OperationalRenderBinding,
    *,
    renderers: Mapping[str, AdaOperationalComponentRenderer],
) -> tuple[Component, ...]:
    if not isinstance(binding, OperationalRenderBinding):
        raise TypeError('Operational component materialization requires OperationalRenderBinding')
    if not isinstance(renderers, Mapping):
        raise TypeError('Operational component renderers must be a mapping')

    expected_keys = binding.component_keys
    expected_key_set = set(expected_keys)
    for component_key, renderer in renderers.items():
        if not isinstance(component_key, str):
            raise TypeError('Operational component renderer key must be a string')
        if component_key not in expected_key_set:
            raise ValueError(f'Unknown operational component renderer: {component_key!r}')
        if not callable(renderer):
            raise TypeError(f'Operational component renderer must be callable: {component_key!r}')

    missing_key = next((key for key in expected_keys if key not in renderers), None)
    if missing_key is not None:
        raise ValueError(f'Missing operational component renderer: {missing_key!r}')

    materialized: list[Component] = []
    for component_binding in binding.components:
        component_key = component_binding.component.key
        rendered = renderers[component_key](binding, component_binding)
        if not isinstance(rendered, Component):
            raise TypeError(
                f'Operational component renderer must return a Dash Component: {component_key!r}'
            )
        materialized.append(rendered)
    return tuple(materialized)
