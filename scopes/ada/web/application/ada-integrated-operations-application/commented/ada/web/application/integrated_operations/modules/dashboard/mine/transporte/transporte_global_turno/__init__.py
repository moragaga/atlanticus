# Exporta la API del subcomponente con lecturas preparadas.
from .definitions import TRANSPORTE_GLOBAL_TURNO_KPI_KEY
from .mapper import map_transporte_global_turno_readings
from .models import TransporteGlobalTurnoState
from .presentation import build_transporte_global_turno

__all__ = [
    'TRANSPORTE_GLOBAL_TURNO_KPI_KEY',
    'TransporteGlobalTurnoState',
    'build_transporte_global_turno',
    'map_transporte_global_turno_readings',
]
