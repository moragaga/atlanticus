from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ExactSourcePublicationResult,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerProjectionCoordinator,
    ManagerProjectionError,
    ManagerSourceConflictError,
    ProjectionAuditRecord,
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


def _snapshot(release_id: str, token: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', f'hash-{release_id}'),
        ),
        concurrency_token=ConcurrencyToken(token),
    )


class ExactWorkflow:
    def __init__(self) -> None:
        self.snapshot = _snapshot('release-1', 'etag-1')
        self.received_snapshot: SourceSnapshot | None = None
        self.audit = ProjectionAuditRecord(
            actor='Admin',
            occurred_at=datetime(2026, 9, 14, 12, 5, tzinfo=UTC),
        )
        self.fail_after_source_change = False

    def get_source_snapshot(self) -> SourceSnapshot:
        return self.snapshot

    def publish_draft_exact(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> ExactSourcePublicationResult:
        self.received_snapshot = expected_source_snapshot
        if self.fail_after_source_change:
            self.snapshot = _snapshot('release-2', 'etag-2')
            raise RuntimeError('publish failed')
        current = self.snapshot.current
        assert current is not None
        release = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.snapshot.source_key,
            release_ref=current.release_ref,
            content_hash=current.content_hash,
            resources=(),
        )
        return ExactSourcePublicationResult(
            source=PublishResult(release=release, snapshot=self.snapshot),
            audit=self.audit,
        )


class LegacyOnlyWorkflow:
    pass


def _coordinator(
    exact_workflow: object,
    *,
    declare_exact_service: bool = True,
    lifecycle_workflow: object | None = None,
) -> ManagerProjectionCoordinator:
    exact_service = 'users.exact-source' if declare_exact_service else None
    module = ManagerModule(
        key='users',
        group_key='configuration',
        title='Usuarios',
        route='/users',
        order=10,
        layout=lambda _services: None,
        workflow_service='users.workflow',
        exact_source_workflow_service=exact_service,
    )
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (module,),
    )
    services = ServiceRegistry()
    services.add('users.workflow', lifecycle_workflow or LegacyOnlyWorkflow())
    if exact_service is not None:
        services.add(exact_service, exact_workflow)
    return ManagerProjectionCoordinator(
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal('local', 'Administrador local', is_local=True)


def test_exact_source_snapshot_is_exposed_without_string_conversion() -> None:
    workflow = ExactWorkflow()
    coordinator = _coordinator(workflow)

    snapshot = coordinator.get_exact_source_snapshot('users', _principal())

    assert snapshot == workflow.snapshot
    assert snapshot.current is not None
    assert snapshot.current.release_ref.release_id == SourceReleaseId('release-1')
    assert snapshot.concurrency_token == ConcurrencyToken('etag-1')


def test_exact_publication_passes_the_same_snapshot_to_workflow() -> None:
    workflow = ExactWorkflow()
    coordinator = _coordinator(workflow)
    expected = workflow.snapshot

    result = coordinator.publish_draft_exact(
        'users',
        _principal(),
        {'revision': 'draft-1'},
        expected,
    )

    assert result.source.snapshot == expected
    assert workflow.received_snapshot == expected


def test_exact_publication_rejects_stale_snapshot_before_workflow_call() -> None:
    workflow = ExactWorkflow()
    coordinator = _coordinator(workflow)
    stale = workflow.snapshot
    workflow.snapshot = _snapshot('release-2', 'etag-2')

    with pytest.raises(
        ManagerSourceConflictError,
        match='changed while the draft was being edited',
    ):
        coordinator.publish_draft_exact(
            'users',
            _principal(),
            {'revision': 'draft-1'},
            stale,
        )

    assert workflow.received_snapshot is None


def test_exact_publication_translates_concurrent_change_after_failure_to_conflict() -> None:
    workflow = ExactWorkflow()
    coordinator = _coordinator(workflow)
    expected = workflow.snapshot
    workflow.fail_after_source_change = True

    with pytest.raises(
        ManagerSourceConflictError,
        match='changed before publication completed',
    ):
        coordinator.publish_draft_exact(
            'users',
            _principal(),
            {'revision': 'draft-1'},
            expected,
        )


def test_exact_source_service_is_resolved_independently_from_lifecycle_service() -> None:
    workflow = ExactWorkflow()
    coordinator = _coordinator(
        workflow,
        lifecycle_workflow=LegacyOnlyWorkflow(),
    )

    assert coordinator.get_exact_source_snapshot('users', _principal()) == workflow.snapshot


def test_exact_source_api_requires_an_explicit_capability_service() -> None:
    workflow = ExactWorkflow()
    coordinator = _coordinator(
        workflow,
        declare_exact_service=False,
        lifecycle_workflow=workflow,
    )

    with pytest.raises(
        ManagerProjectionError,
        match='does not declare an exact source workflow service',
    ):
        coordinator.get_exact_source_snapshot('users', _principal())


def test_exact_source_service_rejects_an_invalid_contract() -> None:
    coordinator = _coordinator(LegacyOnlyWorkflow())

    with pytest.raises(
        ManagerProjectionError,
        match='exact source workflow has an invalid contract',
    ):
        coordinator.get_exact_source_snapshot('users', _principal())
