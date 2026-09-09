from __future__ import annotations

from enum import StrEnum

from .models import ContentState, resolve_content_state


class SourceFreshnessCondition(StrEnum):
    FRESH = 'fresh'
    PREVENTIVE = 'preventive'
    HARD_STALE = 'hard_stale'
    DATA_ERROR = 'data_error'


_FRESHNESS_CONTENT_STATE = {
    SourceFreshnessCondition.FRESH: ContentState.READY,
    SourceFreshnessCondition.PREVENTIVE: ContentState.READY,
    SourceFreshnessCondition.HARD_STALE: ContentState.STALE,
    SourceFreshnessCondition.DATA_ERROR: ContentState.SOURCE_ERROR,
}


def resolve_content_state_from_freshness(
    *conditions: SourceFreshnessCondition,
) -> ContentState:
    if any(not isinstance(condition, SourceFreshnessCondition) for condition in conditions):
        raise TypeError('Freshness resolver requires SourceFreshnessCondition values')
    return resolve_content_state(*(_FRESHNESS_CONTENT_STATE[condition] for condition in conditions))
