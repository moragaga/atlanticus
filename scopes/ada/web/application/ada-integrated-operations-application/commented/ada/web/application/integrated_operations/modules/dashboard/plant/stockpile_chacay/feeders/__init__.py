# Exporta el mapper de Feeders que consume el diccionario preparado.
from .definitions import STOCKPILE_CHACAY_FEEDER_GROUPS, ChacayFeederDefinition
from .mapper import map_chacay_feeders_readings
from .presentation import build_chacay_feeders

__all__ = [
    'STOCKPILE_CHACAY_FEEDER_GROUPS',
    'ChacayFeederDefinition',
    'build_chacay_feeders',
    'map_chacay_feeders_readings',
]
