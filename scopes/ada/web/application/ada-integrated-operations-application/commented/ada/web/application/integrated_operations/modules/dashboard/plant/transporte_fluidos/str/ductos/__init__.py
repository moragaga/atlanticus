# Versión pedagógica: conserva literalmente la lógica y contratos del módulo productivo.

from .definitions import DUCTOS
from .mapper import map_str_ductos_store
from .models import StrDuctReading
from .presentation import build_str_ductos

__all__ = ['DUCTOS', 'StrDuctReading', 'build_str_ductos', 'map_str_ductos_store']
