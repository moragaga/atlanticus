from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from dash import html
from dash.development.base_component import Component

from ada.web.ui.core import component_identity_attributes, subcomponent_identity_attributes

CardDisplayValue: TypeAlias = Component | str | int | float
CardDisplayChildren: TypeAlias = CardDisplayValue | Sequence[CardDisplayValue] | None


def build_card_display(
    *,
    component_key: str,
    wrapper_id: str,
    content: CardDisplayChildren = None,
    regions: CardDisplayChildren = None,
    footer: CardDisplayChildren = None,
    overlay: CardDisplayChildren = None,
    class_name: str | None = None,
) -> Component:
    attributes = component_identity_attributes(component_key)
    return html.Div(
        id=_require_wrapper_id(wrapper_id),
        className=_join_class_names('ada-card-display', class_name),
        **attributes,
        children=[
            html.Div(
                className='ada-card-display__frame',
                children=[
                    html.Div(
                        className='ada-card-display__content',
                        children=_normalize_children(content),
                    ),
                    html.Div(
                        className='ada-card-display__regions',
                        children=_normalize_children(regions),
                    ),
                    html.Div(
                        className='ada-card-display__footer',
                        children=_normalize_children(footer),
                    ),
                ],
            ),
            html.Div(
                className='ada-card-display__overlay',
                children=_normalize_children(overlay),
            ),
        ],
    )


def build_card_display_region(
    *,
    subcomponent_key: str,
    wrapper_id: str,
    children: CardDisplayChildren = None,
    class_name: str | None = None,
) -> Component:
    attributes = subcomponent_identity_attributes(subcomponent_key)
    return html.Div(
        id=_require_wrapper_id(wrapper_id),
        className=_join_class_names('ada-card-display__region', class_name),
        **attributes,
        children=_normalize_children(children),
    )


def _require_wrapper_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Card Display wrapper_id must be a non-empty string')
    return value.strip()


def _normalize_children(value: CardDisplayChildren) -> list[CardDisplayValue]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return [value]


def _join_class_names(*values: str | None) -> str:
    return ' '.join(value.strip() for value in values if isinstance(value, str) and value.strip())
