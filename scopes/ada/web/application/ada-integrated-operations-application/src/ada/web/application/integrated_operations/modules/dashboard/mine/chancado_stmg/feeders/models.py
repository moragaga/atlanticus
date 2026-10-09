from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeederKpiDefinition:
    key: str
    label: str
    percent_kpi_key: str
    color_kpi_key: str | None = None

    def __post_init__(self) -> None:
        for name in ('key', 'label', 'percent_kpi_key'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Feeder {name} must be a non-empty string')
        if self.color_kpi_key is not None and (
            not isinstance(self.color_kpi_key, str) or not self.color_kpi_key.strip()
        ):
            raise ValueError('Feeder color_kpi_key must be a non-empty string or None')
        if self.color_kpi_key == self.percent_kpi_key:
            raise ValueError('Feeder percentage and color KPI keys must be distinct')
