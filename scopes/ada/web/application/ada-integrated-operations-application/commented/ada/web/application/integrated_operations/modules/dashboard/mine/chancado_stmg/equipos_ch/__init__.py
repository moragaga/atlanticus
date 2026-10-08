# Exporta la interfaz del incremento sin establecer todavía el enlace a las claves persistidas.
from .mapper import map_equipos_ch_store
from .models import EquiposChDefinition, EquiposChReading
from .presentation import build_equipos_ch

__all__ = [
    'EquiposChDefinition',
    'EquiposChReading',
    'build_equipos_ch',
    'map_equipos_ch_store',
]
