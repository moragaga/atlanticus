# Versión pedagógica: Tranque conserva sus definiciones originales y consume lecturas compartidas.
from .definitions import TRANQUE_INDICATORS
from .mapper import map_tranque_readings
from .presentation import build_tranque

__all__ = ['TRANQUE_INDICATORS', 'map_tranque_readings', 'build_tranque']
