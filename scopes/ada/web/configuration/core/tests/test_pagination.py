from __future__ import annotations

import pytest

from ada.web.configuration import (
    ALLOWED_CONFIGURATION_PAGE_SIZES,
    DEFAULT_CONFIGURATION_PAGE_SIZE,
    ConfigurationPageRequest,
    SortDirection,
    paginate_items,
)


def test_configuration_page_contract_defaults_to_ten_and_allows_twenty() -> None:
    assert DEFAULT_CONFIGURATION_PAGE_SIZE == 10
    assert ALLOWED_CONFIGURATION_PAGE_SIZES == (10, 20)
    assert ConfigurationPageRequest().page_size == 10
    assert ConfigurationPageRequest(page_size=20).page_size == 20


def test_configuration_page_rejects_unapproved_sizes() -> None:
    with pytest.raises(ValueError, match='page size'):
        ConfigurationPageRequest(page_size=15)


def test_paginate_items_clamps_page_and_reports_range() -> None:
    items = tuple(range(23))
    page = paginate_items(items, ConfigurationPageRequest(page_number=3, page_size=10))

    assert page.items == (20, 21, 22)
    assert page.total_count == 23
    assert page.page_count == 3
    assert page.start_index == 21
    assert page.end_index == 23
    assert page.has_previous
    assert not page.has_next


def test_sort_direction_values_are_stable() -> None:
    assert tuple(item.value for item in SortDirection) == ('asc', 'desc')
