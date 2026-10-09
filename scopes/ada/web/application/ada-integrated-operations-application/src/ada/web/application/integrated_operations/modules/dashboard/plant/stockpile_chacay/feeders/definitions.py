from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChacayFeederDefinition:
    value_kpi_key: str
    color_kpi_key: str | None = None


STOCKPILE_CHACAY_FEEDER_GROUPS = (
    (
        ChacayFeederDefinition('velocidad_feeder015_linea1_real'),
        ChacayFeederDefinition('velocidad_feeder016_linea1_real'),
        ChacayFeederDefinition('velocidad_feeder017_linea1_real'),
        ChacayFeederDefinition('velocidad_feeder018_linea1_real'),
    ),
    (
        ChacayFeederDefinition('velocidad_feeder019_linea2_real'),
        ChacayFeederDefinition('velocidad_feeder020_linea2_real'),
        ChacayFeederDefinition('velocidad_feeder021_linea2_real'),
        ChacayFeederDefinition('velocidad_feeder022_linea2_real'),
    ),
    (
        ChacayFeederDefinition('velocidad_feeder701_linea3_real'),
        ChacayFeederDefinition('velocidad_feeder702_linea3_real'),
        ChacayFeederDefinition('velocidad_feeder703_linea3_real'),
        ChacayFeederDefinition('velocidad_feeder704_linea3_real'),
    ),
    (
        ChacayFeederDefinition('velocidad_feeder5001_linea4_real'),
        ChacayFeederDefinition('velocidad_feeder5002_linea4_real'),
        ChacayFeederDefinition('velocidad_feeder5003_linea4_real'),
        ChacayFeederDefinition('velocidad_feeder5004_linea4_real'),
    ),
)
