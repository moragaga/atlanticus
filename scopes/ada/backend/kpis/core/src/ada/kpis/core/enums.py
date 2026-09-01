from enum import StrEnum


class KpiMode(StrEnum):
    LATEST = 'latest'
    LATEST_NUMBER = 'latest_number'
    SUM = 'sum'
    MAX = 'max'
    STATUS = 'status'
    SUM_LATESTS_NUMBERS = 'sum_latests_numbers'
    MAX_LATESTS_NUMBERS = 'max_latests_numbers'
    CUSTOM = 'custom'
    CONSTANT = 'constant'


class KpiStatus(StrEnum):
    OK = 'ok'
    MISSING = 'missing'
    ERROR = 'error'


class KpiValueKind(StrEnum):
    VALUE = 'value'
    JSON = 'json'


class KpiValueType(StrEnum):
    TEXT = 'text'
    INTEGER = 'integer'
    FLOAT = 'float'
    BOOLEAN = 'boolean'


class KpiArea(StrEnum):
    GENERAL = 'general'
    MINA = 'mina'
    PLANTA = 'planta'
