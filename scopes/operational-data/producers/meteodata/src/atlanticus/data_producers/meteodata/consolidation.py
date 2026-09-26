from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from atlanticus.data_producers.meteodata.models import HM3, Measurement


def consolidate(
    *,
    existing: Mapping[datetime, Mapping[str, Any]],
    measurements: Iterable[Measurement],
) -> dict[datetime, dict[str, Any]]:
    rows: dict[datetime, dict[str, Any]] = {
        timestamp: {
            'timestamp': timestamp,
            'mp10': original.get('mp10'),
            'vel': original.get('vel'),
            'dir': original.get('dir'),
            'estacion_mp10': original.get('estacion_mp10'),
        }
        for timestamp, original in existing.items()
    }
    for sample in measurements:
        row = rows.setdefault(
            sample.timestamp,
            {
                'timestamp': sample.timestamp,
                'mp10': None,
                'vel': None,
                'dir': None,
                'estacion_mp10': None,
            },
        )
        if sample.variable == 'mp10':
            if row['estacion_mp10'] == HM3 and sample.station != HM3:
                continue
            row['mp10'] = sample.value
            row['estacion_mp10'] = sample.station
        else:
            row[sample.variable] = sample.value
    return {timestamp: row for timestamp, row in rows.items() if row != existing.get(timestamp)}
