from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.validation import require_key


@dataclass(frozen=True, slots=True)
class DashboardTimeStatusSourceBinding:
    source_key: str
    label: str
    latest_kpi_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, 'source_key', require_key(self.source_key, label='Source key'))
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Time Status source label must not be empty')
        if not isinstance(self.latest_kpi_key, str) or not self.latest_kpi_key.strip():
            raise ValueError('Time Status latest KPI key must not be empty')
        if self.latest_kpi_key != self.latest_kpi_key.strip():
            raise ValueError('Time Status latest KPI key must be trimmed')
