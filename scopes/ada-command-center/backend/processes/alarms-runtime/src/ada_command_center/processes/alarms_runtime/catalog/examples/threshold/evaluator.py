from __future__ import annotations

import math

from ada_command_center.alarms.core import (
    AffectedInputIssue,
    AlarmEvaluation,
    AlarmStatus,
    EvaluationContext,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
)
from atlanticus.operational_data.core import DataPartition, DataSource

_DEFAULT_LIMIT = 80.0
_EVIDENCE_CONTRACT_KEY = 'mina.threshold'
_EVIDENCE_CONTRACT_VERSION = 'v1'


def evaluate_threshold(context: EvaluationContext) -> AlarmEvaluation:
    frame = context.data.get(DataSource.PI_INTERPOLATED, DataPartition.DAILY)
    observed = frame.last_value_number('temperature')
    if observed is None or not math.isfinite(observed):
        return AlarmEvaluation(
            alarm_identity=context.alarm_identity,
            status=AlarmStatus.ERROR,
            evaluated_at=context.now,
            error=EvaluationError(
                origin=EvaluationErrorOrigin.QUALITY,
                error_key='insufficient_data',
                message='Temperature sample is missing or is not finite',
                affected_inputs=(
                    AffectedInputIssue(
                        reason_key='invalid_temperature_sample',
                        source_key=DataSource.PI_INTERPOLATED.value,
                        scope_key=DataPartition.DAILY.value,
                        fields=('temperature',),
                    ),
                ),
            ),
        )
    limit = context.parameters.get('limit', _DEFAULT_LIMIT)
    return AlarmEvaluation(
        alarm_identity=context.alarm_identity,
        status=AlarmStatus.ACTIVE if observed > limit else AlarmStatus.INACTIVE,
        evaluated_at=context.now,
        evidence_snapshot=EvidenceSnapshot(
            contract_key=_EVIDENCE_CONTRACT_KEY,
            contract_version=_EVIDENCE_CONTRACT_VERSION,
            payload={
                'source': DataSource.PI_INTERPOLATED.value,
                'partition': DataPartition.DAILY.value,
                'column': 'temperature',
                'window_hours': 4,
                'observed_value': observed,
                'limit': limit,
                'comparison': 'greater_than',
            },
        ),
    )
