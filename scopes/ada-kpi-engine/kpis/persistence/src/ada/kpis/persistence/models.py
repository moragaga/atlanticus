from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from ada.kpis.core import KpiEvaluation, KpiWatermark

EVALUATION_BATCH_SCHEMA_VERSION = 1


class KpiEvaluationWriteStatus(StrEnum):
    CREATED = 'created'
    UNCHANGED = 'unchanged'


@dataclass(frozen=True, slots=True)
class KpiEvaluationBatch:
    watermark: KpiWatermark
    evaluations: tuple[KpiEvaluation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.watermark, KpiWatermark):
            raise TypeError('KPI evaluation batch watermark must be KpiWatermark')
        evaluations = tuple(self.evaluations)
        if not evaluations:
            raise ValueError('KPI evaluation batch requires at least one evaluation')
        if not all(isinstance(evaluation, KpiEvaluation) for evaluation in evaluations):
            raise TypeError('KPI evaluation batch must contain KpiEvaluation values')
        if len({evaluation.key for evaluation in evaluations}) != len(evaluations):
            raise ValueError('KPI evaluation batch keys must be unique')
        if any(evaluation.watermark != self.watermark for evaluation in evaluations):
            raise ValueError('KPI evaluation batch watermark must match every evaluation')
        object.__setattr__(self, 'evaluations', evaluations)

    def to_payload(self) -> dict[str, Any]:
        return {
            'schema_version': EVALUATION_BATCH_SCHEMA_VERSION,
            'watermark_utc': self.watermark.to_text(),
            'evaluations': [evaluation.to_payload() for evaluation in self.evaluations],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        if not isinstance(payload, dict):
            raise TypeError('KPI evaluation batch payload must be a dict')
        expected = {'schema_version', 'watermark_utc', 'evaluations'}
        if set(payload) != expected:
            raise ValueError('KPI evaluation batch payload contains unexpected or missing fields')
        if payload['schema_version'] != EVALUATION_BATCH_SCHEMA_VERSION:
            raise ValueError('unsupported KPI evaluation batch schema version')
        evaluations = payload['evaluations']
        if not isinstance(evaluations, list):
            raise TypeError('KPI evaluation batch evaluations must be a list')
        return cls(
            watermark=KpiWatermark.from_text(payload['watermark_utc']),
            evaluations=tuple(KpiEvaluation.from_payload(value) for value in evaluations),
        )


@dataclass(frozen=True, slots=True)
class KpiCommitState:
    watermark: KpiWatermark | None = None

    def to_payload(self) -> dict[str, Any]:
        return {'watermark_utc': None if self.watermark is None else self.watermark.to_text()}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        if not isinstance(payload, dict) or set(payload) != {'watermark_utc'}:
            raise ValueError('KPI commit state payload is invalid')
        value = payload['watermark_utc']
        return cls(None if value is None else KpiWatermark.from_text(value))


@dataclass(frozen=True, slots=True)
class KpiCommitResult:
    before: KpiWatermark | None
    after: KpiWatermark
    write_status: KpiEvaluationWriteStatus
