# Estos enums representan identidades estructurales del contrato, no decisiones de renderizado.
from enum import StrEnum


class ToolConfigurationKind(StrEnum):
    INTEGRATED_OPERATIONS = 'integrated_operations'
    PROCESS = 'process'
    # Strategic se expone como identidad de Tool; sus reglas funcionales pertenecen a sus consumidores.
    STRATEGIC = 'strategic'


class ToolScope(StrEnum):
    MINE = 'mine'
    PLANT = 'plant'


class ProcessLayoutRole(StrEnum):
    LEFT = 'left'
    CENTER = 'center'
    RIGHT = 'right'
    BOTTOM = 'bottom'
