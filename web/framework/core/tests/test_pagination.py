from __future__ import annotations

import pytest

from atlanticus.web.pagination import (
    ALLOWED_PAGE_SIZES,
    DEFAULT_PAGE_SIZE,
    PageRequest,
    paginate_items,
)


def test_page_size_defaults_to_ten_and_allows_twenty() -> None:
    assert DEFAULT_PAGE_SIZE == 10
    assert ALLOWED_PAGE_SIZES == (10, 20)
    assert PageRequest().page_size == 10
    assert PageRequest(page_size=20).page_size == 20


def test_page_request_rejects_unapproved_sizes() -> None:
    with pytest.raises(ValueError, match='Page size'):
        PageRequest(page_size=15)


def test_paginate_items_clamps_page_and_reports_range() -> None:
    items = tuple(range(23))
    page = paginate_items(items, PageRequest(page_number=3, page_size=10))

    assert page.items == (20, 21, 22)
    assert page.total_count == 23
    assert page.page_count == 3
    assert page.start_index == 21
    assert page.end_index == 23
    assert page.has_previous
    assert not page.has_next


def test_empty_pagination_resolves_to_page_one_and_preserves_size() -> None:
    page = paginate_items((), PageRequest(page_number=4, page_size=20))

    assert page.items == ()
    assert page.total_count == 0
    assert page.request.page_number == 1
    assert page.request.page_size == 20
    assert page.page_count == 1
    assert page.start_index == 0
    assert page.end_index == 0
