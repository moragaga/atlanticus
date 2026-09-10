from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component

from ada.web.configuration.pagination import (
    ALLOWED_CONFIGURATION_PAGE_SIZES,
    ConfigurationPage,
)


def build_configuration_pagination(
    page: ConfigurationPage[object],
    *,
    id_prefix: str,
) -> Component:
    if not isinstance(page, ConfigurationPage):
        raise TypeError('Configuration pagination requires a ConfigurationPage')
    prefix = id_prefix.strip() if isinstance(id_prefix, str) else ''
    if not prefix:
        raise ValueError('Configuration pagination id prefix must not be empty')

    return html.Div(
        [
            html.Div(
                _summary(page),
                className='ada-configuration-pagination__summary',
                **{'aria-live': 'polite'},
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        id=f'{prefix}--pagination-previous',
                        type='button',
                        disabled=not page.has_previous,
                        className='ada-configuration-pagination__button',
                        **{'aria-label': 'Página anterior'},
                    ),
                    *_page_buttons(page, id_prefix=prefix),
                    html.Button(
                        '›',
                        id=f'{prefix}--pagination-next',
                        type='button',
                        disabled=not page.has_next,
                        className='ada-configuration-pagination__button',
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='ada-configuration-pagination__navigation',
            ),
            html.Label(
                [
                    html.Span(
                        'Filas',
                        className='ada-configuration-pagination__page-size-label',
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=f'{prefix}--pagination-page-size',
                            options=[
                                {'label': str(value), 'value': value}
                                for value in ALLOWED_CONFIGURATION_PAGE_SIZES
                            ],
                            value=page.request.page_size,
                            clearable=False,
                            searchable=False,
                            style=configuration_dash_select_style(),
                        ),
                        className=(
                            'ada-configuration-dash-select-shell '
                            'ada-configuration-pagination__page-size'
                        ),
                    ),
                ],
                className='ada-configuration-pagination__page-size-control',
            ),
        ],
        className='ada-configuration-pagination',
        **{
            'data-page': str(page.request.page_number),
            'data-page-count': str(page.page_count),
            'data-total-count': str(page.total_count),
        },
    )

def configuration_dash_select_style() -> dict[str, str]:
    return {
        '--Dash-Spacing': '4px',
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-secondary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-secondary)',
        '--Dash-Fill-Interactive-Weak': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Inverse-Strong': 'var(--atlanticus-ui-surface)',
        '--Dash-Text-Primary': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Strong': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Weak': 'var(--atlanticus-ui-text-muted)',
        '--Dash-Text-Disabled': 'var(--atlanticus-ui-text-soft)',
        '--Dash-Fill-Primary-Hover': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Primary-Active': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Disabled': 'var(--atlanticus-ui-border)',
        '--Dash-Shading-Strong': 'rgb(7 21 34 / 25%)',
        '--Dash-Shading-Weak': 'rgb(7 21 34 / 12%)',
    }


def _summary(page: ConfigurationPage[object]) -> str:
    if page.total_count == 0:
        return 'Mostrando 0 de 0'
    return f'Mostrando {page.start_index}–{page.end_index} de {page.total_count}'


def _page_buttons(
    page: ConfigurationPage[object],
    *,
    id_prefix: str,
) -> list[Component]:
    nodes: list[Component] = []
    for value in _visible_page_tokens(
        current=page.request.page_number,
        total=page.page_count,
    ):
        if value is None:
            nodes.append(
                html.Span(
                    '…',
                    className='ada-configuration-pagination__ellipsis',
                    **{'aria-hidden': 'true'},
                )
            )
            continue
        current = value == page.request.page_number
        nodes.append(
            html.Button(
                str(value),
                id={
                    'type': f'{id_prefix}--pagination-page',
                    'index': value,
                },
                type='button',
                disabled=current,
                className=(
                    'ada-configuration-pagination__button '
                    'ada-configuration-pagination__button--active'
                    if current
                    else 'ada-configuration-pagination__button'
                ),
                **{
                    'aria-label': f'Página {value}',
                    'aria-current': 'page' if current else 'false',
                },
            )
        )
    return nodes


def _visible_page_tokens(*, current: int, total: int) -> tuple[int | None, ...]:
    if total <= 7:
        return tuple(range(1, total + 1))

    selected = {1, total, current}
    for candidate in (current - 1, current + 1):
        if 1 < candidate < total:
            selected.add(candidate)

    ordered = sorted(selected)
    tokens: list[int | None] = []
    previous: int | None = None
    for value in ordered:
        if previous is not None and value - previous > 1:
            tokens.append(None)
        tokens.append(value)
        previous = value
    return tuple(tokens)
