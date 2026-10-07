# Espejo comentado: la colección completa se envuelve una sola vez con Content State. El wrapper
# operacional hereda el modo NORMAL/AUTHORING publicado por el layout raíz de ADA Generic.
from __future__ import annotations

from typing import TYPE_CHECKING

from dash import Input, Output, html
from dash.development.base_component import Component

from ada.web.kpis.collector import system_kpi_store_id
from ada.web.shell.header import GLOBAL_INDICATORS_SLOT_ID
from ada.web.ui.content_state import build_content_state_wrapper
from ada.web.ui.global_indicator import build_global_indicator
from atlanticus.web.modules import WebModule

from .bindings import DashboardGlobalIndicatorsRuntimeBinding
from .resolver import (
    ResolvedDashboardGlobalIndicator,
    resolve_dashboard_global_indicators,
    resolve_dashboard_global_indicators_runtime_state,
)

if TYPE_CHECKING:
    from dash import Dash

GLOBAL_INDICATORS_DESTINATION_KEY = 'global_indicators'


def build_dashboard_global_indicators_runtime_component(
    store_data: object,
    *,
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> Component:
    _require_binding(binding)
    resolved = resolve_dashboard_global_indicators(store_data, binding=binding)
    # El grid mantiene todos los indicadores configurados y su metadata de scope.
    grid = html.Div(
        className='ada-global-indicator-grid ada-io-global-indicators',
        **{'data-ada-io-global-indicators-runtime': 'true'},
        children=[_build_placement(item) for item in resolved],
    )
    # El estado declarado y el estado runtime se resuelven para la colección completa.
    return build_content_state_wrapper(
        component_key=None,
        children=grid,
        state=binding.content_state,
        runtime_state=resolve_dashboard_global_indicators_runtime_state(
            store_data,
            binding=binding,
        ),
        operational_runtime=True,
        class_name='ada-io-global-indicators-state',
    )


def create_dashboard_global_indicators_module(
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> WebModule:
    _require_binding(binding)
    store_id = system_kpi_store_id(binding.tool_key, GLOBAL_INDICATORS_DESTINATION_KEY)

    def register_callbacks(dash_app: Dash, _services) -> None:
        @dash_app.callback(
            Output(GLOBAL_INDICATORS_SLOT_ID, 'children'),
            Output(GLOBAL_INDICATORS_SLOT_ID, 'data-slot-empty'),
            Input(store_id, 'data', allow_optional=True),
        )
        def refresh_global_indicators(store_data: object):
            return (
                build_dashboard_global_indicators_runtime_component(
                    store_data,
                    binding=binding,
                ),
                'false',
            )

    return WebModule(
        name='ada-integrated-operations-global-indicators',
        register_callbacks=register_callbacks,
    )


def _build_placement(item: ResolvedDashboardGlobalIndicator) -> Component:
    scopes = item.binding.scopes
    return html.Div(
        build_global_indicator(state=item.state),
        className='ada-io-global-indicator-placement',
        **{
            'data-ada-io-global-indicator-key': item.state.key,
            'data-ada-io-global-indicator-scopes': ','.join(scope.value for scope in scopes),
            'data-ada-io-scope-mine': (
                'true' if any(scope.value == 'mine' for scope in scopes) else 'false'
            ),
            'data-ada-io-scope-plant': (
                'true' if any(scope.value == 'plant' for scope in scopes) else 'false'
            ),
        },
    )


def _require_binding(binding: object) -> None:
    if not isinstance(binding, DashboardGlobalIndicatorsRuntimeBinding):
        raise TypeError('binding must be DashboardGlobalIndicatorsRuntimeBinding')
