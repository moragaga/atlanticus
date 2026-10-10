# Publica las funciones y definiciones del subcomponente.
from .definitions import FLUJO_TREND, VOLUMEN
from .mapper import map_desaladora_readings
from .models import DesaladoraReading
from .presentation import build_desaladora

__all__ = ['FLUJO_TREND', 'VOLUMEN', 'DesaladoraReading', 'build_desaladora', 'map_desaladora_readings']
