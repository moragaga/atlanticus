from datetime import UTC, datetime

import pytest

from atlanticus.web.compositions.users_manager import (
    UsersManagerExactProjectionWorkflow,
    create_users_manager_exact_projection_workflow,
)
from atlanticus.web.manager import ExactProjectionWorkflow
from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionExecutionResult,
    ProjectionRecord,
    ProjectionStatus,
    ProjectionTarget,
)
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationProjectionError


def _release_ref(value: str) -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 15, 19, 0, tzinfo=UTC),
    )


class _Source:
    def __init__(self, source_key: SourceKey, release_ref: SourceReleaseRef) -> None:
        self.source_key = source_key
        self.release_ref = release_ref
        self.requested: list[SourceKey] = []

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        self.requested.append(source_key)
        assert source_key == self.source_key
        return SourceSnapshot(
            source_key=source_key,
            current=SourceReleaseSummary(
                release_ref=self.release_ref,
                content_hash=Digest('sha256', 'hash-release-1'),
            ),
            concurrency_token=ConcurrencyToken('etag-1'),
        )


class _ProjectionStore:
    def get_active(self, _source_key):
        return None

    def replace_active(self, projection):
        return projection


class _ProjectionService:
    def __init__(self, target: ProjectionTarget) -> None:
        self.target = target
        self.selected: list[SourceKey] = []
        self.projected: list[ProjectionTarget] = []
        self.status = ProjectionStatus(
            alignment=ProjectionAlignment.CURRENT,
            source_current_release=target.source_release,
            projected_source_release=target.source_release,
        )

    def get_status(self, source_key: SourceKey) -> ProjectionStatus:
        self.selected.append(source_key)
        return self.status

    def select_current_target(self, source_key: SourceKey) -> ProjectionTarget | None:
        self.selected.append(source_key)
        return self.target

    def project(self, target: ProjectionTarget):
        self.projected.append(target)
        return ProjectionExecutionResult(
            target=target,
            projection=ProjectionRecord(
                source_key=target.source_key,
                source_release_id=target.source_release_id,
                source_published_at_utc=target.source_release.published_at_utc,
                projected_at_utc=datetime(2026, 9, 15, 19, 1, tzinfo=UTC),
                payload=object(),
            ),
        )


def test_factory_binds_explicit_users_source_key_without_legacy_contracts() -> None:
    source_key = SourceKey('users-configuration')
    release_ref = _release_ref('release-1')
    source = _Source(source_key, release_ref)

    workflow = create_users_manager_exact_projection_workflow(
        source=source,
        projection=_ProjectionStore(),
        source_key=source_key,
    )

    assert isinstance(workflow, ExactProjectionWorkflow)
    assert workflow.get_current_projection_target() == ProjectionTarget(source_key, release_ref)
    assert source.requested == [source_key]


def test_workflow_returns_canonical_projection_status_unchanged() -> None:
    source_key = SourceKey('users-configuration')
    target = ProjectionTarget(source_key, _release_ref('release-1'))
    projection = _ProjectionService(target)
    workflow = UsersManagerExactProjectionWorkflow(
        projection=projection,
        source_key=source_key,
    )

    status = workflow.get_status()

    assert status is projection.status
    assert status.alignment is ProjectionAlignment.CURRENT
    assert projection.selected == [source_key]
    assert not hasattr(status, 'source_revision')


def test_workflow_returns_canonical_projection_result_unchanged() -> None:
    source_key = SourceKey('users-configuration')
    target = ProjectionTarget(source_key, _release_ref('release-1'))
    projection = _ProjectionService(target)
    workflow = UsersManagerExactProjectionWorkflow(
        projection=projection,
        source_key=source_key,
    )

    result = workflow.project(target)

    assert result.target == target
    assert result.projection.source_release == target.source_release
    assert projection.projected == [target]
    assert not hasattr(result, 'projection_revision')


def test_workflow_rejects_projection_target_from_another_source() -> None:
    source_key = SourceKey('users-configuration')
    target = ProjectionTarget(source_key, _release_ref('release-1'))
    projection = _ProjectionService(target)
    workflow = UsersManagerExactProjectionWorkflow(
        projection=projection,
        source_key=source_key,
    )
    foreign = ProjectionTarget(
        SourceKey('navigation-configuration'),
        _release_ref('release-2'),
    )

    with pytest.raises(UsersConfigurationProjectionError, match='different source key'):
        workflow.project(foreign)

    assert projection.projected == []
