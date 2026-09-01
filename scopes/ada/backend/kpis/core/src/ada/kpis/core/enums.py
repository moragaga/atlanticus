from enum import StrEnum


class KpiArea(StrEnum):
    GENERAL = 'general'
    MINA = 'mina'
    PLANTA = 'planta'


class KpiMode(StrEnum):
    LATEST = 'latest'
    LATEST_NUMBER = 'latest_number'
    SUM = 'sum'
    MAX = 'max'
    STATUS = 'status'
    CUSTOM = 'custom'


class KpiStatus(StrEnum):
    OK = 'ok'
    MISSING = 'missing'
    ERROR = 'error'


class KpiValueKind(StrEnum):
    VALUE = 'value'
    JSON = 'json'
