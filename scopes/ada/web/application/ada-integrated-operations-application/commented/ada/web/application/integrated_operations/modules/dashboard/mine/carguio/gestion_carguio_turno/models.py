# Modelos del contrato agrupado de Gestión Carguío • Turno.
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)

# Los valores de celdas ya vienen resueltos por backend y Web no los normaliza.
GestionCarguioValue: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class GestionCarguioTurnoRow:
    equipo: str
    fase: GestionCarguioValue
    uebd_pct: GestionCarguioValue
    disponibilidad_fisica_pct: GestionCarguioValue
    rendimiento_efectivo_tph: GestionCarguioValue
    cola_pala_min: GestionCarguioValue
    estado: GestionCarguioValue
    razon: GestionCarguioValue

    def __post_init__(self) -> None:
        if not isinstance(self.equipo, str) or not self.equipo.strip():
            raise ValueError('Gestion Carguio Turno equipo must be a non-empty string')
        for value in (
            self.fase,
            self.uebd_pct,
            self.disponibilidad_fisica_pct,
            self.rendimiento_efectivo_tph,
            self.cola_pala_min,
            self.estado,
            self.razon,
        ):
            if value is not None and not isinstance(value, str | int | float | bool):
                raise TypeError('Gestion Carguio Turno row values must be scalar or null')


@dataclass(frozen=True, slots=True)
class GestionCarguioTurnoSection:
    # La categoría/span es explícita y contiene directamente sus equipos.
    label: str
    rows: tuple[GestionCarguioTurnoRow, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Gestion Carguio Turno section label must be non-empty')
        if not isinstance(self.rows, tuple):
            raise TypeError('Gestion Carguio Turno section rows must be a tuple')
        if any(not isinstance(row, GestionCarguioTurnoRow) for row in self.rows):
            raise TypeError('Gestion Carguio Turno section rows must be rows')


@dataclass(frozen=True, slots=True)
class GestionCarguioTurnoState:
    # Backend controla orden de secciones y orden de equipos dentro de cada sección.
    sections: tuple[GestionCarguioTurnoSection, ...]
    data_state: DashboardDataState

    def __post_init__(self) -> None:
        if not isinstance(self.sections, tuple):
            raise TypeError('Gestion Carguio Turno sections must be a tuple')
        if any(
            not isinstance(section, GestionCarguioTurnoSection)
            for section in self.sections
        ):
            raise TypeError('Gestion Carguio Turno sections must be sections')
        if not isinstance(self.data_state, DashboardDataState):
            raise TypeError('Gestion Carguio Turno data_state must be DashboardDataState')
