from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from ada.kpis.history.contract import HISTORY_SCHEMA_VERSION
from ada.kpis.history.errors import KpiHistoryContractError


# La revisión representa exclusivamente contrato + autoridad Historian confirmada.
def historian_revision(*, watermark_utc: datetime) -> str:
    payload = {
        'schema_version': HISTORY_SCHEMA_VERSION,
        'watermark_utc': historian_watermark_text(watermark_utc),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


# Conserva la autoridad en UTC y exige la misma precisión de segundos que KPI Runtime.
def historian_watermark_text(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError('watermark_utc must be datetime')
    if value.tzinfo is None or value.utcoffset() is None:
        raise KpiHistoryContractError('watermark_utc must be timezone-aware')
    normalized = value.astimezone(UTC)
    if normalized.microsecond != 0:
        raise KpiHistoryContractError('watermark_utc must be aligned to whole seconds')
    return normalized.isoformat(timespec='seconds').replace('+00:00', 'Z')
