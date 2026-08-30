from __future__ import annotations

import pytest

from ada.web.content_state.core import (
    ContentState,
    SourceFreshnessCondition,
    resolve_content_state,
    resolve_content_state_from_freshness,
)


def test_content_state_values_are_stable() -> None:
    assert tuple(state.value for state in ContentState) == (
        'ready',
        'stale',
        'source_error',
        'construction',
    )


def test_content_state_precedence_is_frozen() -> None:
    assert resolve_content_state() is ContentState.READY
    assert resolve_content_state(ContentState.READY, ContentState.STALE) is ContentState.STALE
    assert (
        resolve_content_state(ContentState.STALE, ContentState.SOURCE_ERROR)
        is ContentState.SOURCE_ERROR
    )
    assert (
        resolve_content_state(ContentState.SOURCE_ERROR, ContentState.CONSTRUCTION)
        is ContentState.CONSTRUCTION
    )


def test_content_state_rejects_implicit_string_coercion() -> None:
    with pytest.raises(TypeError, match='requires ContentState values'):
        resolve_content_state('stale')  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ('condition', 'expected'),
    (
        (SourceFreshnessCondition.FRESH, ContentState.READY),
        (SourceFreshnessCondition.PREVENTIVE, ContentState.READY),
        (SourceFreshnessCondition.HARD_STALE, ContentState.STALE),
        (SourceFreshnessCondition.DATA_ERROR, ContentState.SOURCE_ERROR),
    ),
)
def test_freshness_truth_table_is_frozen(
    condition: SourceFreshnessCondition,
    expected: ContentState,
) -> None:
    assert resolve_content_state_from_freshness(condition) is expected


def test_freshness_aggregation_reuses_content_state_precedence() -> None:
    assert (
        resolve_content_state_from_freshness(
            SourceFreshnessCondition.HARD_STALE,
            SourceFreshnessCondition.DATA_ERROR,
        )
        is ContentState.SOURCE_ERROR
    )


def test_freshness_rejects_implicit_string_coercion() -> None:
    with pytest.raises(TypeError, match='requires SourceFreshnessCondition values'):
        resolve_content_state_from_freshness('hard_stale')  # type: ignore[arg-type]
