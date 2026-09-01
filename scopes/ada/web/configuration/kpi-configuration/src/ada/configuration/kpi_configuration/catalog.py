from __future__ import annotations

from dataclasses import dataclass

from ada.configuration.kpi_configuration.errors import KpiConfigurationValidationError
from ada.configuration.kpi_configuration.identity import require_kpi_key


@dataclass(frozen=True, slots=True)
class KpiCatalog:
    revision: str
    kpi_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        revision = self.revision.strip() if isinstance(self.revision, str) else ''
        if not revision:
            raise KpiConfigurationValidationError('KPI catalog revision must not be empty')
        if not isinstance(self.kpi_keys, tuple):
            raise KpiConfigurationValidationError('KPI catalog keys must be a tuple')
        keys = tuple(require_kpi_key(key) for key in self.kpi_keys)
        if len(keys) != len(set(keys)):
            raise KpiConfigurationValidationError('KPI catalog keys must be unique')
        object.__setattr__(self, 'revision', revision)
        object.__setattr__(self, 'kpi_keys', keys)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self.kpi_keys)
