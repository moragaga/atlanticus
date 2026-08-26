from __future__ import annotations

from dash import html

from ada.web.ui.core import component_identity_attributes

from .models import OperationalBrandState
from .module import DEFAULT_OPERATIONAL_BRAND_LOGO_SRC


def build_operational_brand(state: OperationalBrandState) -> html.Div:
    lockup_children = [
        html.Div(
            state.assistant_label,
            className='ada-operational-brand__assistant',
        )
    ]
    if state.context_name is not None:
        lockup_children.append(
            html.Div(
                [
                    html.Span(className='ada-operational-brand__rule'),
                    html.Span(state.context_name),
                    html.Span(className='ada-operational-brand__rule'),
                ],
                className='ada-operational-brand__context',
            )
        )

    return html.Div(
        className='ada-operational-brand',
        **component_identity_attributes('operational_brand'),
        children=[
            html.Img(
                src=state.logo_src or DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
                alt=state.logo_alt,
                title=state.logo_alt,
                className='ada-operational-brand__logo',
            ),
            html.Div(
                lockup_children,
                className='ada-operational-brand__lockup',
            ),
        ],
    )
