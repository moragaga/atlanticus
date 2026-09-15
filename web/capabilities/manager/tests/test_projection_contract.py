from datetime import UTC, datetime

from atlanticus.web.manager.projection import ProjectionState, resolve_projection_state
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus
from atlanticus.web.source.models import SourceReleaseId, SourceReleaseRef


def _release(value: str) -> SourceReleaseRef:
    return SourceReleaseRef(SourceReleaseId(value), datetime(2026, 9, 15, 18, 0, tzinfo=UTC))


def test_projection_state_uses_generic_projection_status_only() -> None:
    release = _release('release-1')
    status = ProjectionStatus(
        alignment=ProjectionAlignment.CURRENT,
        source_current_release=release,
        projected_source_release=release,
    )

    assert resolve_projection_state(status) is ProjectionState.SYNCHRONIZED


def test_projection_state_reports_published_source_pending_projection() -> None:
    status = ProjectionStatus(
        alignment=ProjectionAlignment.NEVER_PROJECTED,
        source_current_release=_release('release-1'),
        projected_source_release=None,
    )

    assert resolve_projection_state(status) is ProjectionState.READY
