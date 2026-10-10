from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrMetricDefinition:
    label: str
    kpi_key: str
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class StrEspesadorDefinition:
    label: str
    state_kpi_key: str
    feed_kpi_key: str
    metrics: tuple[StrMetricDefinition, ...]


def _espesador(number: str, label: str) -> StrEspesadorDefinition:
    prefix = f'tk_{number}'
    return StrEspesadorDefinition(
        label=label,
        state_kpi_key=f'estado_{prefix}_inst',
        feed_kpi_key=f'estado_alimentacion_{prefix}_inst',
        metrics=(
            StrMetricDefinition('Altura', f'altura_{prefix}_inst', '%'),
            StrMetricDefinition('Torque', f'torque_{prefix}_inst', '%'),
            StrMetricDefinition('Pendiente', f'pendiente_{prefix}_inst'),
            StrMetricDefinition('Interfaz', f'interfaz_{prefix}_inst', 'cms'),
        ),
    )


STR_ESPESADORES = (
    _espesador('050', 'TK-50'),
    _espesador('051', 'TK-51'),
    _espesador('712', 'TK-712'),
)
