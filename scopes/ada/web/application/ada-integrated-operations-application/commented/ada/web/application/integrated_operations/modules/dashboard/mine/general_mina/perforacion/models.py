# Modelos internos de Perforación. Los valores de negocio permanecen opacos para Web.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus


@dataclass(frozen=True, slots=True)
class PerforacionComparison:
    real: object
    plan: object
    status: DashboardValueStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, DashboardValueStatus):
            raise TypeError('Perforacion comparison status must be DashboardValueStatus')


@dataclass(frozen=True, slots=True)
class PerforacionResumenState:
    # ERROR puede omitir completamente las métricas.
    data_state: DashboardDataState
    acumulado_semanal: PerforacionComparison | None = None
    plan_semanal: object | None = None
    avance: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.data_state, DashboardDataState):
            raise TypeError('Perforacion resumen data_state must be DashboardDataState')
        if self.data_state is DashboardDataState.ERROR:
            return
        if not isinstance(self.acumulado_semanal, PerforacionComparison):
            raise TypeError('Perforacion resumen acumulado_semanal must be PerforacionComparison')
        # El porcentaje llega listo desde backend; Web no divide, redondea ni limita.
        if self.data_state is DashboardDataState.OK and not isinstance(self.avance, str):
            raise TypeError('Perforacion resumen avance must be a percentage string when data_state is ok')
        if self.avance is not None and not isinstance(self.avance, str):
            raise TypeError('Perforacion resumen avance must be null or a percentage string')


@dataclass(frozen=True, slots=True)
class PerforacionEquipoState:
    perforadora: object
    dia_anterior: PerforacionComparison
    acumulado_semanal: PerforacionComparison

    def __post_init__(self) -> None:
        if not isinstance(self.dia_anterior, PerforacionComparison):
            raise TypeError('Perforacion dia_anterior must be PerforacionComparison')
        if not isinstance(self.acumulado_semanal, PerforacionComparison):
            raise TypeError('Perforacion acumulado_semanal must be PerforacionComparison')


@dataclass(frozen=True, slots=True)
class PerforacionFaseState:
    # Fases y perforadoras son dinámicas y conservan exactamente el orden del backend.
    fase: object
    perforadoras: tuple[PerforacionEquipoState, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.perforadoras, tuple):
            raise TypeError('Perforacion fase perforadoras must be a tuple')


@dataclass(frozen=True, slots=True)
class PerforacionDetalleState:
    data_state: DashboardDataState
    fases: tuple[PerforacionFaseState, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.data_state, DashboardDataState):
            raise TypeError('Perforacion detalle data_state must be DashboardDataState')
        if not isinstance(self.fases, tuple):
            raise TypeError('Perforacion detalle fases must be a tuple')


@dataclass(frozen=True, slots=True)
class PerforacionState:
    # Resumen y detalle mantienen estados de fuente independientes.
    resumen: PerforacionResumenState | None
    resumen_status: DisplayStatus
    detalle: PerforacionDetalleState | None
    detalle_status: DisplayStatus

    def __post_init__(self) -> None:
        if not isinstance(self.resumen_status, DisplayStatus):
            raise TypeError('Perforacion resumen_status must be DisplayStatus')
        if not isinstance(self.detalle_status, DisplayStatus):
            raise TypeError('Perforacion detalle_status must be DisplayStatus')
        if self.resumen is None and self.resumen_status is DisplayStatus.OK:
            raise ValueError('Perforacion resumen cannot be null when resumen_status is OK')
        if self.resumen is not None and self.resumen_status is not DisplayStatus.OK:
            raise ValueError('Perforacion resumen_status must be OK when resumen is present')
        if self.detalle is None and self.detalle_status is DisplayStatus.OK:
            raise ValueError('Perforacion detalle cannot be null when detalle_status is OK')
        if self.detalle is not None and self.detalle_status is not DisplayStatus.OK:
            raise ValueError('Perforacion detalle_status must be OK when detalle is present')
