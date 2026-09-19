from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerProjectionCoordinator,
    ManagerSourceConflictError,
    SourcePublicationResult,
    SourceReadResult,
)
from atlanticus.web.manager.projection import ProjectionAuditRecord
from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionExecutionResult,
    ProjectionRecord,
    ProjectionStatus,
    ProjectionTarget,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot(release: str, token: str) -> SourceSnapshot:
    ref = SourceReleaseRef(SourceReleaseId(release), datetime(2026, 9, 15, 18, 0, tzinfo=UTC))
    return SourceSnapshot(
        source_key=SourceKey('tools'),
        current=SourceReleaseSummary(ref, Digest('sha256', 'a' * 64)),
        concurrency_token=ConcurrencyToken(token),
    )


class SourceWorkflow:
    def __init__(self, snapshot: SourceSnapshot) -> None:
        self.snapshot = snapshot
        self.expected_snapshots: list[SourceSnapshot] = []

    def get_source_snapshot(self) -> SourceSnapshot:
        return self.snapshot

    def publish_draft(self, payload, expected_source_snapshot):
        self.expected_snapshots.append(expected_source_snapshot)
        ref = SourceReleaseRef(
            SourceReleaseId('release-2'), datetime(2026, 9, 15, 18, 1, tzinfo=UTC)
        )
        next_snapshot = SourceSnapshot(
            source_key=SourceKey('tools'),
            current=SourceReleaseSummary(ref, Digest('sha256', 'b' * 64)),
            concurrency_token=ConcurrencyToken('token-2'),
        )
        self.snapshot = next_snapshot
        release = SourceReleaseMetadata(
            schema_version=1,
            source_key=SourceKey('tools'),
            release_ref=ref,
            content_hash=next_snapshot.current.content_hash,
            resources=(),
            basis_release=expected_source_snapshot.current.release_ref,
        )
        return SourcePublicationResult(
            source=PublishResult(release=release, snapshot=next_snapshot),
            audit=ProjectionAuditRecord('tester', datetime(2026, 9, 15, 18, 1, tzinfo=UTC)),
        )


class Reader:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def load_current_source(self):
        return SourceReadResult(self.snapshot, {'enabled': True})


class Projection:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_status(self, source_key):
        assert source_key == SourceKey('tools')
        return ProjectionStatus(
            ProjectionAlignment.NEVER_PROJECTED, self.snapshot.current.release_ref, None
        )

    def select_current_target(self, source_key):
        return ProjectionTarget(source_key, self.snapshot.current.release_ref)

    def project(self, target):
        return ProjectionExecutionResult(
            target=target,
            projection=ProjectionRecord(
                source_key=target.source_key,
                source_release_id=target.source_release_id,
                source_published_at_utc=target.source_release.published_at_utc,
                projected_at_utc=datetime(2026, 9, 15, 18, 2, tzinfo=UTC),
                payload={'enabled': True},
            ),
        )


class Validation:
    def validate_draft(self, payload):
        raise AssertionError('Not used in this test')


def _coordinator(snapshot):
    module = ManagerModule(
        key='tools',
        group_key='configuration',
        title='Tools',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        source_key=SourceKey('tools'),
        source_service='tools.source',
        source_reader_service='tools.reader',
        projection_service='tools.projection',
        draft_validation_service='tools.validation',
        access_key='tools.manage',
    )
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),), (module,)
    )
    services = ServiceRegistry()
    source = SourceWorkflow(snapshot)
    services.add('tools.source', source)
    services.add('tools.reader', Reader(snapshot))
    services.add('tools.projection', Projection(snapshot))
    services.add('tools.validation', Validation())
    coordinator = ManagerProjectionCoordinator(
        registry=registry, services=services, authorization=DefaultManagerAuthorizationPolicy()
    )
    return coordinator, source


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal('local', 'Local', access_keys=('tools.manage',), is_local=True)


def test_coordinator_routes_projection_with_projection_target() -> None:
    coordinator, _source = _coordinator(_snapshot('release-1', 'token-1'))

    target = coordinator.get_current_projection_target('tools', _principal())
    result = coordinator.project('tools', _principal(), target)

    assert result.target == target
    assert result.projection.source_release_id == SourceReleaseId('release-1')


def test_publication_uses_current_token_when_release_is_unchanged() -> None:
    original = _snapshot('release-1', 'token-1')
    coordinator, source = _coordinator(original)
    current = _snapshot('release-1', 'token-current')
    source.snapshot = current

    coordinator.publish_draft('tools', _principal(), {'enabled': False}, original)

    assert source.expected_snapshots == [current]


def test_publication_rejects_changed_source_release() -> None:
    original = _snapshot('release-1', 'token-1')
    coordinator, source = _coordinator(original)
    source.snapshot = _snapshot('release-other', 'token-other')

    with pytest.raises(ManagerSourceConflictError, match='source changed'):
        coordinator.publish_draft('tools', _principal(), {'enabled': False}, original)
