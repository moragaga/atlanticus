from __future__ import annotations

from dash import html

from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
    DashboardSharedCardBinding,
)
from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_card_id,
    dashboard_component_id,
)
from ada.web.ui.card_display import build_card_display


# El panel conserva únicamente composición y título; la apariencia de card pertenece a Card Display.
def build_component_panel(binding: DashboardComponentBinding):
    return html.Section(
        [
            html.Div(binding.label, className='ada-io-component__title'),
            html.Div(
                [
                    build_dashboard_card(
                        card,
                        tool_component_key=binding.tool_component_key,
                    )
                    for card in binding.cards
                ],
                className='ada-io-component__cards',
            ),
        ],
        id=dashboard_component_id(binding.key),
        className=f'ada-io-component ada-io-component--{binding.key}',
        **_component_attributes(binding),
    )


# Esta función sólo traduce el binding local al contrato reusable; no implementa otra card.
def build_dashboard_card(
    binding: DashboardCardBinding,
    *,
    tool_component_key: str,
):
    return _build_card_display(
        key=binding.key,
        label=binding.label,
        tool_component_key=tool_component_key,
        tool_subcomponent_key=binding.tool_subcomponent_key,
    )


# La card compartida usa la misma primitive y agrega únicamente los vínculos declarados por Tool.
def build_shared_dashboard_card(binding: DashboardSharedCardBinding):
    return _build_card_display(
        key=binding.key,
        label=binding.label,
        tool_component_key=binding.tool_component_key,
        tool_subcomponent_key=binding.tool_subcomponent_key,
        linked_tool_component_keys=binding.linked_tool_component_keys,
    )


# Un único helper concentra el mapeo desde identidad Tool hacia ada-web-ui-card-display.
def _build_card_display(
    *,
    key: str,
    label: str,
    tool_component_key: str,
    tool_subcomponent_key: str,
    linked_tool_component_keys: tuple[str, ...] = (),
):
    return build_card_display(
        component_key=tool_component_key,
        subcomponent_key=tool_subcomponent_key,
        linked_component_keys=linked_tool_component_keys,
        wrapper_id=dashboard_card_id(key),
        # El id interno sigue siendo el target estable donde luego se montará contenido KPI.
        content=html.Div(id=dashboard_card_content_id(key)),
        footer=label,
    )


def _component_attributes(binding: DashboardComponentBinding) -> dict[str, str]:
    # El panel expone scope e identidad de componente para consumidores transversales.
    return {
        'data-ada-io-component-key': binding.key,
        'data-ada-operational-scope': binding.scope.value,
        'data-ada-component-key': binding.tool_component_key,
    }
