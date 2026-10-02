# Utilidades puras para normalizar fechas UTC y calcular revisiones determinísticas con JSON canónico.
# published_at queda fuera de los payloads que se entregan a canonical_revision desde los projectores.

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ada.kpis.delivery.errors import KpiDeliveryValidationError


def require_aware_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f'{field_name} must be datetime')
    if value.tzinfo is None or value.utcoffset() is None:
        raise KpiDeliveryValidationError(f'{field_name} must be timezone-aware')
    return value.astimezone(UTC)


def utc_iso(value: datetime, *, field_name: str) -> str:
    normalized = require_aware_datetime(value, field_name=field_name)
    return normalized.isoformat().replace('+00:00', 'Z')


def canonical_revision(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        raise TypeError('payload must be a mapping')
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise KpiDeliveryValidationError('payload must be canonical JSON data') from exc
    return hashlib.sha256(encoded).hexdigest()
