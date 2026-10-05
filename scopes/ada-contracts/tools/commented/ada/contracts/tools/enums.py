# Este módulo conserva los enums contractuales de Tools. Sus valores serializados no cambian durante la migración de ownership.
# La lógica se mantiene equivalente al archivo productivo; sólo se agregan comentarios pedagógicos.

from enum import StrEnum


class ToolConfigurationKind(StrEnum):
    INTEGRATED_OPERATIONS = 'integrated_operations'
    PROCESS = 'process'
    STRATEGIC = 'strategic'


class ToolScope(StrEnum):
    MINE = 'mine'
    PLANT = 'plant'
