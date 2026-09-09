from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from typing import Generic, TypeVar

DEFAULT_CONFIGURATION_PAGE_SIZE = 10
ALLOWED_CONFIGURATION_PAGE_SIZES = (10, 20)

_ItemT = TypeVar('_ItemT')


class SortDirection(StrEnum):
    ASC = 'asc'
    DESC = 'desc'


@dataclass(frozen=True, slots=True)
class ConfigurationPageRequest:
    page_number: int = 1
    page_size: int = DEFAULT_CONFIGURATION_PAGE_SIZE

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or not isinstance(self.page_number, int):
            raise ValueError('Configuration page number must be an integer')
        if self.page_number < 1:
            raise ValueError('Configuration page number must be greater than zero')
        if isinstance(self.page_size, bool) or not isinstance(self.page_size, int):
            raise ValueError('Configuration page size must be an integer')
        if self.page_size not in ALLOWED_CONFIGURATION_PAGE_SIZES:
            raise ValueError(
                f'Configuration page size must be one of {ALLOWED_CONFIGURATION_PAGE_SIZES}'
            )

    @property
    def offset(self) -> int:
        return (self.page_number - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class ConfigurationPage(Generic[_ItemT]):
    items: tuple[_ItemT, ...]
    total_count: int
    request: ConfigurationPageRequest

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if isinstance(self.total_count, bool) or not isinstance(self.total_count, int):
            raise ValueError('Configuration total count must be an integer')
        if self.total_count < 0:
            raise ValueError('Configuration total count must not be negative')
        if not isinstance(self.request, ConfigurationPageRequest):
            raise ValueError('Configuration page request is invalid')
        if len(items) > self.request.page_size:
            raise ValueError('Configuration page contains more items than the requested page size')
        if self.total_count == 0:
            if items:
                raise ValueError('Empty configuration result must not contain page items')
            if self.request.page_number != 1:
                raise ValueError('Empty configuration result must use page one')
        elif self.request.page_number > self.page_count:
            raise ValueError('Configuration page number exceeds the available page count')
        object.__setattr__(self, 'items', items)

    @property
    def page_count(self) -> int:
        return max(1, ceil(self.total_count / self.request.page_size))

    @property
    def has_previous(self) -> bool:
        return self.request.page_number > 1

    @property
    def has_next(self) -> bool:
        return self.request.page_number < self.page_count

    @property
    def start_index(self) -> int:
        if not self.items:
            return 0
        return self.request.offset + 1

    @property
    def end_index(self) -> int:
        if not self.items:
            return 0
        return self.request.offset + len(self.items)


def paginate_items(
    items: tuple[_ItemT, ...],
    request: ConfigurationPageRequest,
) -> ConfigurationPage[_ItemT]:
    if not isinstance(request, ConfigurationPageRequest):
        raise ValueError('Configuration page request is invalid')
    resolved = tuple(items)
    total_count = len(resolved)
    if total_count == 0:
        empty_request = ConfigurationPageRequest(
            page_number=1,
            page_size=request.page_size,
        )
        return ConfigurationPage(items=(), total_count=0, request=empty_request)
    page_count = max(1, ceil(total_count / request.page_size))
    page_number = min(request.page_number, page_count)
    resolved_request = ConfigurationPageRequest(
        page_number=page_number,
        page_size=request.page_size,
    )
    start = resolved_request.offset
    end = start + resolved_request.page_size
    return ConfigurationPage(
        items=resolved[start:end],
        total_count=total_count,
        request=resolved_request,
    )
