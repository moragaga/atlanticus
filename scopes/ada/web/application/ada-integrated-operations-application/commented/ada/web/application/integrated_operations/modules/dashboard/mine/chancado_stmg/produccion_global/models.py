# Cada lectura conserva tanto su clave para inspección como el estado DisplayValue.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.display_status import DisplayValue


@dataclass(frozen=True, slots=True)
class ProduccionGlobalMetric:
    kpi_key: str
    value: DisplayValue


@dataclass(frozen=True, slots=True)
class ProduccionGlobalRow:
    key: str
    label: str
    real: ProduccionGlobalMetric
    plan_acumulado: ProduccionGlobalMetric
    proyeccion: ProduccionGlobalMetric
    plan_dia: ProduccionGlobalMetric
    requerido_hora: ProduccionGlobalMetric


@dataclass(frozen=True, slots=True)
class ProduccionGlobalState:
    rows: tuple[ProduccionGlobalRow, ...]
