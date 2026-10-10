# Versión pedagógica: STA conserva su API de presentación y usa el mapeo de lecturas preparado en el componente.
from .definitions import STA_INDICATORS
from .mapper import map_sta_readings
from .presentation import build_sta

__all__ = ['STA_INDICATORS', 'map_sta_readings', 'build_sta']
