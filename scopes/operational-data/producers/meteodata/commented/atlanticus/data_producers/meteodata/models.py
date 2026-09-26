from __future__ import annotations

# Objetos inmutables para desacoplar adquisición, consolidación y persistencia.
import math
from dataclasses import dataclass
from datetime import datetime

HM = 'mlp_es_hm'
HM3 = 'mlp_es_hm3'
QUERIES = ((HM, 'mp10'), (HM3, 'mp10'), (HM, 'vel'), (HM, 'dir'))


@dataclass(frozen=True, slots=True)
class Projection:
    timestamp: datetime
    promedio_dia_mp10: float
    proyeccion_mp10: float
    monitoreo_oficial: bool

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)
        for value in (self.promedio_dia_mp10, self.proyeccion_mp10):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError('projection measurements must be numeric')
            if not math.isfinite(value):
                raise ValueError('projection measurements must be finite')
        if not isinstance(self.monitoreo_oficial, bool):
            raise ValueError('monitoreo_oficial must be boolean')


@dataclass(frozen=True, slots=True)
class Measurement:
    timestamp: datetime
    station: str
    variable: str
    value: float

    def __post_init__(self) -> None:
        _require_utc(self.timestamp)
        if (self.station, self.variable) not in QUERIES:
            raise ValueError('unsupported Meteodata station-variable combination')
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise ValueError('measurement must be numeric')
        if not math.isfinite(self.value):
            raise ValueError('measurement must be finite')


@dataclass(frozen=True, slots=True)
class Acquisition:
    measurements: tuple[Measurement, ...]
    failed_queries: tuple[str, ...]
    successful_queries: int


def _require_utc(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamp must be timezone-aware UTC')
    if value.utcoffset().total_seconds() != 0:
        raise ValueError('timestamp must use UTC')
