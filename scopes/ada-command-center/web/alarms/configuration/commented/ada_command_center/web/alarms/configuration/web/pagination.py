from __future__ import annotations

from collections.abc import Mapping

from dash import html

from ada_command_center.web.alarms.configuration.web.ids import (
    LIST_PAGE_SIZE_TYPE,
    LIST_PAGE_TYPE,
)
from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, Page, PageRequest, paginate_items

# Cada lista guarda su propia página y tamaño de página.
LIST_NAMES = frozenset({'families', 'rules', 'messages', 'global'})


def list_page(
    items: tuple[object, ...], navigation: Mapping[str, object], name: str
) -> Page[object]:
    if name not in LIST_NAMES:
        raise ValueError('Unknown Alarm Configuration list')
    state = navigation.get('pagination')
    page_state = state.get(name) if isinstance(state, dict) else None
    values = page_state if isinstance(page_state, dict) else {}
    size = values.get('size', 10)
    number = values.get('page', 1)
    if type(size) is not int or size not in ALLOWED_PAGE_SIZES:
        size = 10
    if type(number) is not int or number < 1:
        number = 1
    return paginate_items(items, PageRequest(page_number=number, page_size=size))


def change_list_page(
    navigation: Mapping[str, object], name: str, *, page: int | None = None, size: int | None = None
) -> dict[str, object]:
    if name not in LIST_NAMES:
        raise ValueError('Unknown Alarm Configuration list')
    original = navigation.get('pagination')
    pages = dict(original) if isinstance(original, dict) else {}
    previous = pages.get(name)
    current = dict(previous) if isinstance(previous, dict) else {'page': 1, 'size': 10}
    if size is not None:
        if type(size) is not int or size not in ALLOWED_PAGE_SIZES:
            raise ValueError('Unsupported page size')
        current.update(page=1, size=size)
    elif page is not None:
        if type(page) is not int or page < 1:
            raise ValueError('Invalid page number')
        current['page'] = page
    else:
        raise ValueError('A page or page size is required')
    pages[name] = current
    return {**navigation, 'pagination': pages}


def list_pagination(page: Page[object], name: str) -> object:
    if name not in LIST_NAMES:
        raise ValueError('Unknown Alarm Configuration list')
    controls = []
    for number in page_tokens(page.request.page_number, page.page_count):
        if number is None:
            controls.append(html.Span('…', className='alarm-page__ellipsis'))
            continue
        current = number == page.request.page_number
        controls.append(
            html.Button(
                str(number),
                id={'type': LIST_PAGE_TYPE, 'listing': name, 'page': number, 'action': 'page'},
                type='button',
                n_clicks=0,
                disabled=current,
                className='alarm-page__button alarm-page__button--active'
                if current
                else 'alarm-page__button',
                **{'aria-current': 'page' if current else 'false'},
            )
        )
    return html.Nav(
        [
            html.Span(
                f'{page.start_index}–{page.end_index} de {page.total_count}'
                if page.total_count
                else '0 elementos',
                className='alarm-page__summary',
                **{'aria-live': 'polite'},
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        id={
                            'type': LIST_PAGE_TYPE,
                            'listing': name,
                            'page': page.request.page_number - 1,
                            'action': 'previous',
                        },
                        n_clicks=0,
                        type='button',
                        disabled=not page.has_previous,
                        className='alarm-page__button',
                        **{'aria-label': 'Página anterior'},
                    ),
                    *controls,
                    html.Button(
                        '›',
                        id={
                            'type': LIST_PAGE_TYPE,
                            'listing': name,
                            'page': page.request.page_number + 1,
                            'action': 'next',
                        },
                        n_clicks=0,
                        type='button',
                        disabled=not page.has_next,
                        className='alarm-page__button',
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='alarm-page__controls',
            ),
            html.Div(
                [
                    html.Span('Filas', className='alarm-page__summary'),
                    *[
                        html.Button(
                            str(size),
                            id={'type': LIST_PAGE_SIZE_TYPE, 'listing': name, 'size': size},
                            type='button',
                            n_clicks=0,
                            disabled=page.request.page_size == size,
                            className='alarm-page__button alarm-page__button--active'
                            if page.request.page_size == size
                            else 'alarm-page__button',
                        )
                        for size in ALLOWED_PAGE_SIZES
                    ],
                ],
                className='alarm-page__controls',
            ),
        ],
        className='alarm-page',
        **{'aria-label': f'Paginación de {name}'},
    )


def page_tokens(current: int, count: int) -> tuple[int | None, ...]:
    if count <= 7:
        return tuple(range(1, count + 1))
    selected = {1, count, current - 1, current, current + 1}
    if current <= 3:
        selected.update((2, 3, 4))
    if current >= count - 2:
        selected.update((count - 3, count - 2, count - 1))
    values = sorted(v for v in selected if 1 <= v <= count)
    result: list[int | None] = []
    previous = 0
    for number in values:
        if previous and number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return tuple(result)
