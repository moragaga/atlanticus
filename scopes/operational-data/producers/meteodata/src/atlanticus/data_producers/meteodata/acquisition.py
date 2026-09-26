from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Protocol

from atlanticus.connectivity.http import HttpError
from atlanticus.data_producers.meteodata.errors import (
    MeteodataAcquisitionError,
    MeteodataResponseError,
)
from atlanticus.data_producers.meteodata.models import Acquisition, Measurement, Projection, QUERIES

_FIXED_API_TZ = timezone(timedelta(hours=-4))
_TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'
TIMESTAMP_MODES = frozenset({'epoch_utc', 'fixed_gmt_minus_four_wall_clock'})


class JsonHttpClient(Protocol):
    def request_json(self, method: str, endpoint: str, **kwargs: Any) -> Any: ...


class MeteodataAcquirer:
    def __init__(self, *, client: JsonHttpClient, projection_timestamp_mode: str) -> None:
        if projection_timestamp_mode not in TIMESTAMP_MODES:
            raise ValueError('unsupported Meteodata projection timestamp mode')
        self.client = client
        self.projection_timestamp_mode = projection_timestamp_mode

    def acquire_projection(self) -> Projection:
        response = self.client.request_json('GET', 'consultas', params={'op': 'proyeccion'})
        if not isinstance(response, Mapping):
            raise MeteodataResponseError('projection response must be an object')
        ts_last = response.get('ts_last')
        if isinstance(ts_last, bool) or not isinstance(ts_last, int) or ts_last < 0:
            raise MeteodataResponseError('projection ts_last must be Unix milliseconds')
        try:
            timestamp = datetime.fromtimestamp(ts_last / 1000, tz=UTC)
            if self.projection_timestamp_mode == 'fixed_gmt_minus_four_wall_clock':
                timestamp = timestamp.replace(tzinfo=_FIXED_API_TZ).astimezone(UTC)
            return Projection(
                timestamp=timestamp,
                promedio_dia_mp10=_number(response.get('promedio_dia')),
                proyeccion_mp10=_number(response.get('proyeccion')),
                monitoreo_oficial=response.get('monitoreo_oficial'),
            )
        except (ValueError, OverflowError, OSError) as error:
            raise MeteodataResponseError('invalid Meteodata projection response') from error

    def acquire_data(
        self,
        *,
        now_utc: datetime,
        lookback_minutes: int,
        check_cancelled: Callable[[], None] | None = None,
    ) -> Acquisition:
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise ValueError('now_utc must be timezone-aware')
        if isinstance(lookback_minutes, bool) or not isinstance(lookback_minutes, int) or lookback_minutes <= 0:
            raise ValueError('lookback_minutes must be a positive integer')
        end = now_utc.astimezone(_FIXED_API_TZ).replace(second=0, microsecond=0)
        start = end - timedelta(minutes=lookback_minutes)
        base_params = {
            'op': 'datos',
            'tini': start.strftime('%Y%m%d_%H%M%S'),
            'tfin': end.strftime('%Y%m%d_%H%M%S'),
        }
        samples: list[Measurement] = []
        failures: list[str] = []
        succeeded = 0
        for station, variable in QUERIES:
            if check_cancelled is not None:
                check_cancelled()
            try:
                response = self.client.request_json(
                    'GET',
                    'consultas',
                    params={**base_params, 'est': station, 'var': variable},
                )
                samples.extend(_parse_data(response, station=station, variable=variable))
                succeeded += 1
            except (HttpError, MeteodataResponseError):
                failures.append(f'{station}.{variable}')
        if succeeded == 0:
            raise MeteodataAcquisitionError('all Meteodata measurement queries failed')
        return Acquisition(tuple(samples), tuple(failures), succeeded)


def _parse_data(payload: Any, *, station: str, variable: str) -> list[Measurement]:
    if not isinstance(payload, Mapping) or payload.get('estacion') != station or payload.get('variable') != variable:
        raise MeteodataResponseError('Meteodata station or variable response mismatch')
    rows = payload.get('datos')
    if not isinstance(rows, list):
        raise MeteodataResponseError('Meteodata datos must be an array')
    result: list[Measurement] = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2 or not isinstance(row[0], str):
            raise MeteodataResponseError('invalid Meteodata measurement row')
        try:
            timestamp = datetime.strptime(row[0], _TIMESTAMP_FORMAT).replace(tzinfo=_FIXED_API_TZ).astimezone(UTC)
            if row[1] is None:
                continue
            result.append(Measurement(timestamp, station, variable, _number(row[1])))
        except (ValueError, OverflowError) as error:
            raise MeteodataResponseError('invalid Meteodata measurement row') from error
    return result


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError('expected a numeric Meteodata measurement')
    result = float(value)
    if not (-float('inf') < result < float('inf')):
        raise ValueError('expected a finite Meteodata measurement')
    return result
