from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from ada.kpis.history.errors import KpiHistoryContractError
from ada.kpis.history.revision import historian_revision, historian_watermark_text

HISTORIAN_AUTHORITY_SCHEMA_VERSION = 1
HISTORIAN_AUTHORITY_NAMESPACE = ('kpis', 'history')
HISTORIAN_AUTHORITY_NAME = 'authority'


@dataclass(frozen=True, slots=True)
class KpiHistorianAuthority:
    watermark_utc: datetime

    def __post_init__(self) -> None:
        text = historian_watermark_text(self.watermark_utc)
        normalized = datetime.fromisoformat(text.replace('Z', '+00:00'))
        object.__setattr__(self, 'watermark_utc', normalized)

    @property
    def revision(self) -> str:
        return historian_revision(watermark_utc=self.watermark_utc)

    def to_payload(self) -> dict[str, Any]:
        return {
            'schema_version': HISTORIAN_AUTHORITY_SCHEMA_VERSION,
            'watermark_utc': historian_watermark_text(self.watermark_utc),
            'revision': self.revision,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Self:
        if not isinstance(payload, Mapping):
            raise TypeError('KPI historian authority payload must be a mapping')
        expected = {'schema_version', 'watermark_utc', 'revision'}
        if set(payload) != expected:
            raise KpiHistoryContractError(
                'KPI historian authority payload contains unexpected or missing fields'
            )
        if payload['schema_version'] != HISTORIAN_AUTHORITY_SCHEMA_VERSION:
            raise KpiHistoryContractError('unsupported KPI historian authority schema version')
        watermark_text = payload['watermark_utc']
        if not isinstance(watermark_text, str):
            raise KpiHistoryContractError('KPI historian authority watermark_utc is invalid')
        try:
            watermark = datetime.fromisoformat(watermark_text.replace('Z', '+00:00'))
            authority = cls(watermark_utc=watermark)
        except (TypeError, ValueError, KpiHistoryContractError) as error:
            raise KpiHistoryContractError(
                'KPI historian authority watermark_utc is invalid'
            ) from error
        revision = payload['revision']
        if not isinstance(revision, str) or revision != authority.revision:
            raise KpiHistoryContractError('KPI historian authority revision is invalid')
        return authority
