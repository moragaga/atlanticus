# Modela el catálogo mínimo de identidades KPI.
# Este archivo es el espejo pedagógico del código productivo equivalente.

from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.registry.errors import KpiRegistryValidationError
from ada.web.kpis.registry.identity import require_kpi_key


@dataclass(frozen=True, slots=True)
class KpiCatalog:
    kpi_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kpi_keys, tuple):
            raise KpiRegistryValidationError('KPI catalog keys must be a tuple')
        keys = tuple(require_kpi_key(key) for key in self.kpi_keys)
        if len(keys) != len(set(keys)):
            raise KpiRegistryValidationError('KPI catalog keys must be unique')
        object.__setattr__(self, 'kpi_keys', keys)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self.kpi_keys)
