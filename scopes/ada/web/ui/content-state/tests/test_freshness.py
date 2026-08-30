from __future__ import annotations

from importlib.resources import files

import pytest

from ada.web.ui.content_state import (
    ContentState,
    SourceFreshnessCondition,
    resolve_content_state_from_freshness,
)


def test_source_freshness_condition_values_are_stable() -> None:
    assert tuple(condition.value for condition in SourceFreshnessCondition) == (
        'fresh',
        'preventive',
        'hard_stale',
        'data_error',
    )


@pytest.mark.parametrize(
    ('condition', 'expected'),
    (
        (SourceFreshnessCondition.FRESH, ContentState.READY),
        (SourceFreshnessCondition.PREVENTIVE, ContentState.READY),
        (SourceFreshnessCondition.HARD_STALE, ContentState.STALE),
        (SourceFreshnessCondition.DATA_ERROR, ContentState.SOURCE_ERROR),
    ),
)
def test_freshness_policy_maps_each_condition_to_content_state(
    condition: SourceFreshnessCondition,
    expected: ContentState,
) -> None:
    assert resolve_content_state_from_freshness(condition) is expected


def test_freshness_policy_defaults_to_ready_without_dependencies() -> None:
    assert resolve_content_state_from_freshness() is ContentState.READY


def test_freshness_policy_uses_content_state_precedence_across_dependencies() -> None:
    assert (
        resolve_content_state_from_freshness(
            SourceFreshnessCondition.FRESH,
            SourceFreshnessCondition.HARD_STALE,
        )
        is ContentState.STALE
    )
    assert (
        resolve_content_state_from_freshness(
            SourceFreshnessCondition.HARD_STALE,
            SourceFreshnessCondition.DATA_ERROR,
        )
        is ContentState.SOURCE_ERROR
    )


def test_freshness_policy_rejects_implicit_string_coercion() -> None:
    with pytest.raises(TypeError, match='requires SourceFreshnessCondition values'):
        resolve_content_state_from_freshness('hard_stale')  # type: ignore[arg-type]


def test_freshness_policy_does_not_import_time_status() -> None:
    source = files('ada.web.ui.content_state').joinpath('freshness.py').read_text(encoding='utf-8')

    assert 'ada.web.ui.time_status' not in source
    assert 'pi' not in source.lower()
    assert 'dispatch' not in source.lower()
