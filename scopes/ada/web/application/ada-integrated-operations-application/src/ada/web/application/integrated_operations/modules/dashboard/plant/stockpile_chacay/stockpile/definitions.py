from __future__ import annotations

from dataclasses import dataclass

from ada.web.ui.stockpile import StockpileDefinition, StockpileVariant

STOCKPILE_CHACAY_POSITION_KEY = 'posicion_carro'
STOCKPILE_CHACAY_POSITIONS = tuple(range(1, 9))
STOCKPILE_CHACAY_PILE_POSITIONS = (2, 4, 6, 8)


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

STOCKPILE_CHACAY_ROWS = (
    ChacayRowDefinition('plan', 'Plan', 'ton_stockpile_plan'),
    ChacayRowDefinition('capacidad', 'Capacidad', 'ton_stockpile_capacidad'),
    ChacayRowDefinition('real', 'Real', 'ton_stockpile_real'),
    ChacayRowDefinition('lidar', 'LIDAR', 'toneladas_stockpile_lidar'),
)
