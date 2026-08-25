from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import TypeVar, overload

from atlanticus.web.errors import ServiceRegistryError

T = TypeVar('T')


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, object] = {}
        self._frozen = False

    def add(self, name: str, service: object) -> None:
        normalized = name.strip()
        if not normalized:
            raise ServiceRegistryError('Service name must not be empty')
        if self._frozen:
            raise ServiceRegistryError('Service registry is frozen')
        if normalized in self._services:
            raise ServiceRegistryError(f'Service already registered: {normalized}')
        self._services[normalized] = service

    @overload
    def require(self, name: str) -> object: ...

    @overload
    def require(self, name: str, expected_type: type[T]) -> T: ...

    def require(self, name: str, expected_type: type[T] | None = None) -> object | T:
        normalized = name.strip()
        if normalized not in self._services:
            raise ServiceRegistryError(f'Service is not registered: {normalized}')
        service = self._services[normalized]
        if expected_type is not None and not isinstance(service, expected_type):
            raise ServiceRegistryError(f'Service has an unexpected type: {normalized}')
        return service

    def contains(self, name: str) -> bool:
        return name.strip() in self._services

    def freeze(self) -> None:
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    def snapshot(self) -> Mapping[str, object]:
        return MappingProxyType(dict(self._services))

    def __len__(self) -> int:
        return len(self._services)

    def __iter__(self) -> Iterator[str]:
        return iter(self._services)
