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
from ada.web.content_state import ContentState
from ada.web.ui.card_display import build_card_display
from ada.web.ui.content_state import build_content_state_wrapper


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
        content_state=binding.content_state,
    )


def build_shared_dashboard_card(binding: DashboardSharedCardBinding):
    return _build_card_display(
        key=binding.key,
        label=binding.label,
        tool_component_key=binding.tool_component_key,
        tool_subcomponent_key=binding.tool_subcomponent_key,
        linked_component_keys=binding.linked_tool_component_keys,
    )


def _build_card_display(
    *,
    key: str,
    label: str,
    tool_component_key: str,
    tool_subcomponent_key: str,
    linked_component_keys: tuple[str, ...] = (),
    content_state: ContentState = ContentState.READY,
):
    card = build_card_display(
        component_key=tool_component_key,
        subcomponent_key=tool_subcomponent_key,
        linked_component_keys=linked_component_keys,
        wrapper_id=dashboard_card_id(key),
        content=html.Div(id=dashboard_card_content_id(key)),
        footer=label,
    )
    return build_content_state_wrapper(
        component_key=None,
        children=card,
        state=content_state,
        operational_runtime=True,
        class_name='ada-io-card-state',
    )


def _component_attributes(binding: DashboardComponentBinding) -> dict[str, str]:
    return {
        'data-ada-io-component-key': binding.key,
        'data-ada-operational-scope': binding.scope.value,
        'data-ada-component-key': binding.tool_component_key,
    }
