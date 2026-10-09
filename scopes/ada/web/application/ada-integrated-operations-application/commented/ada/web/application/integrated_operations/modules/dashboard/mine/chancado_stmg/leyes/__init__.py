# API pública del módulo de Leyes, independiente de los otros bloques de Chancado.
from .definitions import LEYES_DEFINITIONS
from .mapper import map_leyes_store
from .presentation import build_leyes_summary

__all__ = ['LEYES_DEFINITIONS', 'build_leyes_summary', 'map_leyes_store']
