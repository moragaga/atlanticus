from __future__ import annotations

from dataclasses import dataclass


# Claves y orden de KPI recuperados desde las referencias legacy indicadas.
# Define localmente los KPI de Puerto, sin depender de la tarjeta Desaladora.
@dataclass(frozen=True, slots=True)
class MetricDefinition:
    label: str
    kpi_key: str
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class TankDefinition:
    label: str
    level_key: str
    color_key: str


@dataclass(frozen=True, slots=True)
class FilterDefinition:
    label: str
    state_key: str


@dataclass(frozen=True, slots=True)
class ShipmentDefinition:
    tonnage: MetricDefinition
    duration_key: str
    state_key: str


FILTRADO_TREND = MetricDefinition('Filtrado', 'filtrado_real_mean_hora')
FILTRADO_ACCUMULATED = MetricDefinition('Filtrado acumulado día', 'filtrado_acumulado_dia')
TANKS = tuple(
    TankDefinition(f'TK-{number}', f'nivel_tk_0{number}_inst', f'tk{number}_nivel_color')
    for number in ('60', '61', '62', '63')
)
FILTERS = tuple(
    FilterDefinition(f'FL-{number}', f'fl_{number}_estado_inst')
    for number in ('001', '002', '003', '004', '005', '006', '702', '703')
)
SHIPMENT = ShipmentDefinition(
    MetricDefinition('Tonelaje', 'embarque_tonelaje_actual_inst', 'TMH'),
    'embarque_tiempo_actual_inst',
    'embarque_estado_inst',
)
