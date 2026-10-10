# Expone el contrato de definiciones y el consumo/presentación de Producción Global.
from .definitions import PRODUCCION_GLOBAL_DEFINITIONS
from .mapper import map_produccion_global_readings
from .presentation import build_produccion_global

__all__ = [
    'PRODUCCION_GLOBAL_DEFINITIONS',
    'build_produccion_global',
    'map_produccion_global_readings',
]
