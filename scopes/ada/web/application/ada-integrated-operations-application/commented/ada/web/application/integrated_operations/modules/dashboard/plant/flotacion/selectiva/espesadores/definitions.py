from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
# Punto de responsabilidad: EspesadorMetricDefinition; mantiene el mismo contrato que producción.
class EspesadorMetricDefinition:
    label: str
    kpi_key: str
    unit: str


@dataclass(frozen=True, slots=True)
# Punto de responsabilidad: EspesadorDefinition; mantiene el mismo contrato que producción.
class EspesadorDefinition:
    label: str
    state_kpi_key: str
    feed_kpi_key: str
    metrics: tuple[EspesadorMetricDefinition, ...]


# Punto de responsabilidad: _espesador; mantiene el mismo contrato que producción.
def _espesador(number: str) -> EspesadorDefinition:
    prefix = f'tk_{number}'
    return EspesadorDefinition(
        label=f'TK-{number}',
        state_kpi_key=f'{prefix}_estado_inst',
        feed_kpi_key=f'{prefix}_estado_alimentacion_inst',
        metrics=(
            EspesadorMetricDefinition('Altura', f'{prefix}_altura_inst', '%'),
            EspesadorMetricDefinition('Torque', f'{prefix}_torque_inst', '%'),
            EspesadorMetricDefinition('Flujo', f'{prefix}_flujo_inst', 't/h'),
            EspesadorMetricDefinition('Sólido', f'{prefix}_solido_inst', '%'),
        ),
    )


# La secuencia y las claves corresponden al diseño actual del legacy.
ESPESADORES = tuple(_espesador(number) for number in ('10', '12', '13', '55', '56'))
