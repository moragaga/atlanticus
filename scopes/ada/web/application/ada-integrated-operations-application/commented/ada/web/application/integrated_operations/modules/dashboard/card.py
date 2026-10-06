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


# El renderer consume contratos compartidos, pero no es dueño del catálogo Mine/Plant.
def build_component_panel(binding: DashboardComponentBinding):
    return html.Section(
        [
            html.Div(binding.label, className='ada-io-component__title'),
            html.Div(
                [
                    build_dashboard_card(
                        card,
                        tool_component_key=binding.tool_component_key,
                        scope=binding.scope.value,
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
    tool_component_key: str | None,
    scope: str,
):
    attributes = {
        'data-ada-io-card-key': binding.key,
        'data-ada-operational-scope': scope,
    }
    if tool_component_key is not None:
        attributes['data-ada-component-key'] = tool_component_key
    if binding.tool_subcomponent_key is not None:
        attributes['data-ada-subcomponent-key'] = binding.tool_subcomponent_key

    return html.Article(
        [
            html.Div(
                id=dashboard_card_content_id(binding.key),
                className='ada-io-card__content',
            ),
            html.Div(binding.label, className='ada-io-card__footer'),
        ],
        id=dashboard_card_id(binding.key),
        className='ada-io-card',
        **attributes,
    )


def build_shared_dashboard_card(binding: DashboardSharedCardBinding):
    attributes = {
        'data-ada-io-card-key': binding.key,
        'data-ada-operational-scope': binding.scope.value,
    }
    if binding.tool_component_key is not None:
        attributes['data-ada-component-key'] = binding.tool_component_key
    if binding.tool_subcomponent_key is not None:
        attributes['data-ada-subcomponent-key'] = binding.tool_subcomponent_key
    if binding.linked_tool_component_keys:
        attributes['data-ada-linked-component-keys'] = ' '.join(
            binding.linked_tool_component_keys
        )

    return html.Article(
        [
            html.Div(
                id=dashboard_card_content_id(binding.key),
                className='ada-io-card__content',
            ),
            html.Div(binding.label, className='ada-io-card__footer'),
        ],
        id=dashboard_card_id(binding.key),
        className='ada-io-card ada-io-card--shared',
        **attributes,
    )


def _component_attributes(binding: DashboardComponentBinding) -> dict[str, str]:
    attributes = {
        'data-ada-io-component-key': binding.key,
        'data-ada-operational-scope': binding.scope.value,
    }
    if binding.tool_component_key is not None:
        attributes['data-ada-component-key'] = binding.tool_component_key
    return attributes
