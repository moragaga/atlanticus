# Versión pedagógica: Ductos expone un mapper alimentado por lecturas compartidas.
from .definitions import DUCTOS
from .mapper import map_str_ductos_readings
from .models import StrDuctReading
from .presentation import build_str_ductos

__all__ = ['DUCTOS', 'StrDuctReading', 'build_str_ductos', 'map_str_ductos_readings']
