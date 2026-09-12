from datetime import UTC, datetime, timedelta, timezone

import pytest

from atlanticus.web.projection.models import (
    ProjectionAttemptOutcome,
    ProjectionExecutionResult,
    ProjectionRecord,
    ProjectionTarget,
)
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def _release_ref(value: str = 'release-1') -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 12, 12, tzinfo=UTC),
    )


def test_projection_record_exposes_durable_source_release_id_and_resolvable_ref() -> None:
    record = ProjectionRecord(
        source_key=SourceKey('navigation'),
        source_release_id=SourceReleaseId('release-1'),
        source_published_at_utc=datetime(2026, 9, 12, 9, tzinfo=timezone(timedelta(hours=-3))),
        projected_at_utc=datetime(2026, 9, 12, 10, tzinfo=timezone(timedelta(hours=-3))),
        payload={'value': 1},
    )

    assert record.source_release_id == SourceReleaseId('release-1')
    assert record.source_release == SourceReleaseRef(
        release_id=SourceReleaseId('release-1'),
        published_at_utc=datetime(2026, 9, 12, 12, tzinfo=UTC),
    )
    assert record.projected_at_utc == datetime(2026, 9, 12, 13, tzinfo=UTC)


def test_projection_record_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match='Source publication time must be timezone-aware'):
        ProjectionRecord(
            source_key=SourceKey('navigation'),
            source_release_id=SourceReleaseId('release-1'),
            source_published_at_utc=datetime(2026, 9, 12, 12),
            projected_at_utc=datetime(2026, 9, 12, 13, tzinfo=UTC),
            payload='payload',
        )


def test_success_result_requires_exact_target_provenance() -> None:
    target = ProjectionTarget(source_key=SourceKey('navigation'), source_release=_release_ref())
    record = ProjectionRecord(
        source_key=target.source_key,
        source_release_id=target.source_release_id,
        source_published_at_utc=target.source_release.published_at_utc,
        projected_at_utc=datetime(2026, 9, 12, 13, tzinfo=UTC),
        payload='payload',
    )

    result = ProjectionExecutionResult(target=target, projection=record)

    assert result.outcome is ProjectionAttemptOutcome.SUCCESS


def test_success_result_rejects_different_release() -> None:
    target = ProjectionTarget(
        source_key=SourceKey('navigation'),
        source_release=_release_ref('release-1'),
    )
    record = ProjectionRecord(
        source_key=target.source_key,
        source_release_id=SourceReleaseId('release-2'),
        source_published_at_utc=target.source_release.published_at_utc,
        projected_at_utc=datetime(2026, 9, 12, 13, tzinfo=UTC),
        payload='payload',
    )

    with pytest.raises(ValueError, match='Projection result source release does not match target'):
        ProjectionExecutionResult(target=target, projection=record)
