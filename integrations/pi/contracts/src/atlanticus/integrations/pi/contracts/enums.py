from enum import StrEnum


class PiExtractionMode(StrEnum):
    INTERPOLATED = 'interpolated'
    RECORDED = 'recorded'


class PiMaterialization(StrEnum):
    LATEST = 'latest'
    DAILY = 'daily'
    MONTHLY = 'monthly'


class PiValueKind(StrEnum):
    FLOAT = 'float'
    TEXT = 'text'
