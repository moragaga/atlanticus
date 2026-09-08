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


# Los Components guardan un acento semántico; el branding resolverá su apariencia final.
class ToolComponentAccent(StrEnum):
    BLUE = 'blue'
    CYAN = 'cyan'
    GREEN = 'green'
    GOLD = 'gold'
    ORANGE = 'orange'
    RED = 'red'
    GRAY = 'gray'
    PURPLE = 'purple'
