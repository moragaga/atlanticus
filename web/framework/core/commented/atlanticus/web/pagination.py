from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Generic, TypeVar

# La paginación es un contrato transversal de Atlanticus: define el tamaño y la
# posición de una página, pero no decide cómo debe representarla ninguna UI.
DEFAULT_PAGE_SIZE = 10
ALLOWED_PAGE_SIZES = (10, 20)

_ItemT = TypeVar('_ItemT')


@dataclass(frozen=True, slots=True)
class PageRequest:
    # El request mantiene sólo estado de navegación. Filtros, búsqueda y
    # ordenamiento siguen perteneciendo al consumidor que construye la lista.
    page_number: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or not isinstance(self.page_number, int):
            raise ValueError('Page number must be an integer')
        if self.page_number < 1:
            raise ValueError('Page number must be greater than zero')
        if isinstance(self.page_size, bool) or not isinstance(self.page_size, int):
            raise ValueError('Page size must be an integer')
        if self.page_size not in ALLOWED_PAGE_SIZES:
            raise ValueError(f'Page size must be one of {ALLOWED_PAGE_SIZES}')

    @property
    def offset(self) -> int:
        return (self.page_number - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class Page(Generic[_ItemT]):
    # Page contiene únicamente registros reales. Los placeholders que estabilizan
    # una tabla de 10 o 20 filas son responsabilidad exclusiva de cada presentación.
    items: tuple[_ItemT, ...]
    total_count: int
    request: PageRequest

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if isinstance(self.total_count, bool) or not isinstance(self.total_count, int):
            raise ValueError('Pagination total count must be an integer')
        if self.total_count < 0:
            raise ValueError('Pagination total count must not be negative')
        if not isinstance(self.request, PageRequest):
            raise ValueError('Pagination page request is invalid')
        if len(items) > self.request.page_size:
            raise ValueError('Page contains more items than the requested page size')
        if self.total_count == 0:
            if items:
                raise ValueError('Empty pagination result must not contain page items')
            if self.request.page_number != 1:
                raise ValueError('Empty pagination result must use page one')
        elif self.request.page_number > self.page_count:
            raise ValueError('Page number exceeds the available page count')
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
    request: PageRequest,
) -> Page[_ItemT]:
    # El helper recorta una colección ya resuelta por el consumidor. Si una
    # mutación elimina la última página, ajusta el número solicitado a la última
    # página válida sin inventar elementos vacíos.
    if not isinstance(request, PageRequest):
        raise ValueError('Pagination page request is invalid')
    resolved = tuple(items)
    total_count = len(resolved)
    if total_count == 0:
        empty_request = PageRequest(
            page_number=1,
            page_size=request.page_size,
        )
        return Page(items=(), total_count=0, request=empty_request)
    page_count = max(1, ceil(total_count / request.page_size))
    page_number = min(request.page_number, page_count)
    resolved_request = PageRequest(
        page_number=page_number,
        page_size=request.page_size,
    )
    start = resolved_request.offset
    end = start + resolved_request.page_size
    return Page(
        items=resolved[start:end],
        total_count=total_count,
        request=resolved_request,
    )
