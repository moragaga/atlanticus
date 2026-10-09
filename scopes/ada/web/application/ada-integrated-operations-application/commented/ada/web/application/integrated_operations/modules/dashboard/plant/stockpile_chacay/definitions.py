from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.stockpile import StockpileDefinition, StockpileVariant

# El contrato inicial conserva las claves legacy sin introducir equivalencias.
STOCKPILE_CHACAY_POSITION_KEY = 'posicion_carro'
STOCKPILE_CHACAY_POSITIONS = tuple(range(1, 9))


@dataclass(frozen=True, slots=True)
class ChacayPileDefinition:
    label: str
    kpi_key: str
    graphic: StockpileDefinition


@dataclass(frozen=True, slots=True)
class ChacayRowDefinition:
    key: str
    label: str
    kpi_key: str


# Las cuatro pilas reutilizan el perfil fijo hasta conocer la escala real en metros.
STOCKPILE_CHACAY_PILES = tuple(
    ChacayPileDefinition(
        label=letter,
        kpi_key=f'nivel_pila_{letter}_stock',
        graphic=StockpileDefinition(
            key=f'stockpile_chacay_{letter.lower()}',
            variant=StockpileVariant.FIXED_PROFILE,
        ),
    )
    for letter in ('G', 'H', 'I', 'J')
)

# Orden de los cuatro KPI inferiores, cada uno en su propia fila.
STOCKPILE_CHACAY_ROWS = (
    ChacayRowDefinition('plan', 'Plan', 'ton_stockpile_plan'),
    ChacayRowDefinition('capacidad', 'Capacidad', 'ton_stockpile_capacidad'),
    ChacayRowDefinition('real', 'Real', 'ton_stockpile_real'),
    ChacayRowDefinition('lidar', 'LIDAR', 'toneladas_stockpile_lidar'),
)
