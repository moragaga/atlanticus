# Contratos de los valores independientes de los chancadores.
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
    rendimiento_kpi_key: str
    min_atollo_kpi_key: str
    min_poste_kpi_key: str
    rendimiento_color_kpi_key: str | None = None
    min_atollo_color_kpi_key: str | None = None
    min_poste_color_kpi_key: str | None = None

    def __post_init__(self) -> None:
        for name in (
            'key', 'label', 'state_kpi_key', 'throughput_kpi_key', 'atollo_kpi_key',
            'atollo_active_value', 'atollo_inactive_value',
            'rendimiento_kpi_key', 'min_atollo_kpi_key', 'min_poste_kpi_key',
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Equipos CH {name} must be a non-empty string')
        if self.atollo_active_value.strip().lower() == self.atollo_inactive_value.strip().lower():
            raise ValueError('Equipos CH atollo states must be distinct')
        for name in (
            'rendimiento_color_kpi_key', 'min_atollo_color_kpi_key',
            'min_poste_color_kpi_key',
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f'Equipos CH {name} must be null or a non-empty string')
        if len({
            self.state_kpi_key, self.throughput_kpi_key, self.atollo_kpi_key,
            self.rendimiento_kpi_key, self.min_atollo_kpi_key, self.min_poste_kpi_key,
        }) != 6:
            raise ValueError('Equipos CH KPI keys must be distinct')


@dataclass(frozen=True, slots=True)
class EquiposChReading:
    definition: EquiposChDefinition
    state: DisplayValue
    throughput: DisplayValue
    atollo: DisplayValue
    rendimiento: DisplayValue
    min_atollo: DisplayValue
    min_poste: DisplayValue
    rendimiento_color: DisplayValue | None = None
    min_atollo_color: DisplayValue | None = None
    min_poste_color: DisplayValue | None = None
