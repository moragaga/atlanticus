# Exporta la API del subcomponente con lecturas preparadas.
from .definitions import NUMERO_OPERATIVO_TURNO_KPI_KEY
from .mapper import map_numero_operativo_turno_readings
from .models import NumeroOperativoTurnoState
from .presentation import build_numero_operativo_turno

__all__ = [
    'NUMERO_OPERATIVO_TURNO_KPI_KEY',
    'NumeroOperativoTurnoState',
    'build_numero_operativo_turno',
    'map_numero_operativo_turno_readings',
]
