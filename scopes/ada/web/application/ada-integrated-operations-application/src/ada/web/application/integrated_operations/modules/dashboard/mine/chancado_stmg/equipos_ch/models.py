from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue


@dataclass(frozen=True, slots=True)
class EquiposChDefinition:
    key: str
    label: str
    state_kpi_key: str
    throughput_kpi_key: str
    atollo_kpi_key: str
    atollo_active_value: str
    atollo_inactive_value: str

    def __post_init__(self) -> None:
        for name in (
            'key', 'label', 'state_kpi_key', 'throughput_kpi_key', 'atollo_kpi_key',
            'atollo_active_value', 'atollo_inactive_value',
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Equipos CH {name} must be a non-empty string')
        if self.atollo_active_value.strip().lower() == self.atollo_inactive_value.strip().lower():
            raise ValueError('Equipos CH atollo states must be distinct')
        if len({self.state_kpi_key, self.throughput_kpi_key, self.atollo_kpi_key}) != 3:
            raise ValueError('Equipos CH KPI keys must be distinct')


@dataclass(frozen=True, slots=True)
class EquiposChReading:
    definition: EquiposChDefinition
    state: DisplayValue
    throughput: DisplayValue
    atollo: DisplayValue
