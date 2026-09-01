# Catálogo explícito: KPI base primero y Over KPI en orden declarado. No existe autodiscovery ni ordenamiento implícito.
from __future__ import annotations

from collections.abc import Iterable, Iterator

from ada.kpis.core.rules import KpiSpec, OverKpiSpec


class KpiCatalog:
    def __init__(
        self,
        specs: Iterable[KpiSpec],
        over_specs: Iterable[OverKpiSpec] = (),
    ) -> None:
        resolved_specs = tuple(specs)
        resolved_over_specs = tuple(over_specs)
        if not all(isinstance(spec, KpiSpec) for spec in resolved_specs):
            raise TypeError('KPI catalog specs must contain KpiSpec values')
        if not all(isinstance(spec, OverKpiSpec) for spec in resolved_over_specs):
            raise TypeError('KPI catalog over_specs must contain OverKpiSpec values')
        keys = tuple(spec.key for spec in resolved_specs) + tuple(
            spec.key for spec in resolved_over_specs
        )
        if len(set(keys)) != len(keys):
            raise ValueError('KPI catalog keys must be unique')
        available = {spec.key for spec in resolved_specs}
        for spec in resolved_over_specs:
            missing = tuple(key for key in spec.dependencies if key not in available)
            if missing:
                raise ValueError(
                    f'{spec.key}: Over KPI dependencies must reference base or prior Over KPIs'
                )
            available.add(spec.key)
        self._specs = resolved_specs
        self._over_specs = resolved_over_specs
        self._by_key = {spec.key: spec for spec in (*resolved_specs, *resolved_over_specs)}

    def __len__(self) -> int:
        return len(self._specs) + len(self._over_specs)

    def __iter__(self) -> Iterator[KpiSpec]:
        return iter(self._specs)

    @property
    def specs(self) -> tuple[KpiSpec, ...]:
        return self._specs

    @property
    def over_specs(self) -> tuple[OverKpiSpec, ...]:
        return self._over_specs

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self._specs) + tuple(
            spec.key for spec in self._over_specs
        )

    @property
    def persisted_history_keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in (*self._specs, *self._over_specs) if spec.persist_history)

    def get(self, key: str) -> KpiSpec | OverKpiSpec:
        try:
            return self._by_key[key]
        except KeyError as error:
            raise KeyError(f'unknown KPI key: {key}') from error
