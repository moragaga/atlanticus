from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from dash import page_registry


def _clear_dash_pages() -> None:
    for module_name in tuple(page_registry):
        sys.modules.pop(module_name, None)
    page_registry.clear()


@pytest.fixture(autouse=True)
def isolate_dash_page_registry() -> Iterator[None]:
    _clear_dash_pages()
    yield
    _clear_dash_pages()
