# Espejo comentado de enums de Tools R2.

from enum import StrEnum


class ToolConfigurationKind(StrEnum):
    INTEGRATED_OPERATIONS = 'integrated_operations'
    PROCESS = 'process'
    STRATEGIC = 'strategic'


class ToolScope(StrEnum):
    MINE = 'mine'
    PLANT = 'plant'


class ProcessLayoutRole(StrEnum):
    LEFT = 'left'
    CENTER = 'center'
    RIGHT = 'right'
    BOTTOM = 'bottom'
