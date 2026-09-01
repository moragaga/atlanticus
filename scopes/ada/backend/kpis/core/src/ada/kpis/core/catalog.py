from __future__ import annotations

from collections.abc import Iterable, Iterator

from ada.kpis.core.rules import KpiSpec


class KpiCatalog:
    def __init__(self, specs: Iterable[KpiSpec]) -> None:
        resolved = tuple(specs)
        if not all(isinstance(spec, KpiSpec) for spec in resolved):
            raise TypeError('KPI catalog must contain KpiSpec values')
        by_key = {spec.key: spec for spec in resolved}
        if len(by_key) != len(resolved):
            raise ValueError('KPI catalog keys must be unique')
        self._specs = resolved
        self._by_key = by_key

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self) -> Iterator[KpiSpec]:
        return iter(self._specs)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self._specs)

    def get(self, key: str) -> KpiSpec:
        try:
            return self._by_key[key]
        except KeyError as error:
            raise KeyError(f'unknown KPI key: {key}') from error
