from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    DraftValidationResult,
    ManagerAuthorizationError,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerProjectionCoordinator,
    ManagerSourceConflictError,
    ProjectionAuditRecord,
    ProjectionExecutionResult,
    ProjectionStatus,
    RevisionHistoryEntry,
    SourcePublicationResult,
    SourceVerificationResult,
    build_draft_revision,
)
from atlanticus.web.services import ServiceRegistry


class Workflow:
    def __init__(self) -> None:
        self.audit = ProjectionAuditRecord(
            actor='Admin',
            occurred_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        )

    def get_status(self) -> ProjectionStatus:
        return ProjectionStatus('source', self.audit)

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        return DraftValidationResult(build_draft_revision(payload), True, self.audit)

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        assert expected_source_revision == 'source'
        return SourcePublicationResult(build_draft_revision(payload), True, self.audit)

    def project(self, expected_source_revision: str) -> ProjectionExecutionResult:
        return ProjectionExecutionResult(
            source_revision=expected_source_revision,
            projection_revision='projection',
            projected=True,
            audit=self.audit,
        )

    def load_revision(self, revision: str) -> dict[str, object]:
        return {'revision': revision}

    def list_history(self, *, limit: int = 20) -> tuple[RevisionHistoryEntry, ...]:
        return (
            RevisionHistoryEntry(
                revision='source',
                saved_by='Admin',
                saved_at=self.audit.occurred_at,
            ),
        )[:limit]


def test_coordinator_orchestrates_draft_publish_projection_and_history() -> None:
    module = ManagerModule(
        key='tools',
        group_key='configuration',
        title='Herramientas',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        workflow_service='tools.workflow',
    )
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (module,),
    )
    services = ServiceRegistry()
    services.add('tools.workflow', Workflow())
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    coordinator = ManagerProjectionCoordinator(
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )
    payload = {'tools': []}

    assert coordinator.get_status('tools', principal).source_revision == 'source'
    validation = coordinator.validate_draft('tools', principal, payload)
    assert validation.valid
    publication = coordinator.publish_draft('tools', principal, payload, 'source')
    assert publication.source_revision == build_draft_revision(payload)
    assert coordinator.project('tools', principal, 'source').projection_revision == 'projection'
    assert coordinator.list_history('tools', principal)[0].revision == 'source'
    assert coordinator.load_history_revision('tools', principal, 'source') == {'revision': 'source'}


class MutableWorkflow(Workflow):
    def __init__(self, source_revision: str | None = 'source-b') -> None:
        super().__init__()
        self.source_revision = source_revision
        self.payloads = {
            'source-a': {'value': 'a'},
            'source-b': {'value': 'b'},
            'source-c': {'value': 'c'},
        }
        self.published_expected: str | None = None

    def get_status(self) -> ProjectionStatus:
        if self.source_revision is None:
            return ProjectionStatus()
        return ProjectionStatus(self.source_revision, self.audit)

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        self.published_expected = expected_source_revision
        return SourcePublicationResult(build_draft_revision(payload), True, self.audit)

    def load_revision(self, revision: str) -> dict[str, object]:
        return self.payloads[revision]


def _coordinator_for(workflow: Workflow, *, force_publish_enabled: bool = False):
    module = ManagerModule(
        key='tools',
        group_key='configuration',
        title='Herramientas',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        workflow_service='tools.workflow',
        force_publish_enabled=force_publish_enabled,
    )
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (module,),
    )
    services = ServiceRegistry()
    services.add('tools.workflow', workflow)
    return ManagerProjectionCoordinator(
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )


def test_publish_reports_source_conflict_before_writing() -> None:
    workflow = MutableWorkflow('source-b')
    coordinator = _coordinator_for(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    with pytest.raises(ManagerSourceConflictError, match='source changed'):
        coordinator.publish_draft('tools', principal, {'value': 'draft'}, 'source-a')

    assert workflow.published_expected is None


def test_current_source_loads_exact_published_revision_with_audit() -> None:
    workflow = MutableWorkflow('source-b')
    coordinator = _coordinator_for(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    snapshot = coordinator.load_current_source('tools', principal)

    assert snapshot.revision == 'source-b'
    assert snapshot.payload == {'value': 'b'}
    assert snapshot.audit.actor == 'Admin'


def test_force_publish_requires_enabled_module_and_uses_current_revision() -> None:
    workflow = MutableWorkflow('source-b')
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    disabled = _coordinator_for(workflow)

    with pytest.raises(ManagerAuthorizationError, match='force publication is not enabled'):
        disabled.force_publish_draft(
            'tools',
            principal,
            {'value': 'mine'},
            base_source_revision='source-a',
            expected_source_revision='source-b',
        )

    enabled = _coordinator_for(workflow, force_publish_enabled=True)
    result = enabled.force_publish_draft(
        'tools',
        principal,
        {'value': 'mine'},
        base_source_revision='source-a',
        expected_source_revision='source-b',
    )

    assert result.published is True
    assert workflow.published_expected == 'source-b'


def test_verify_source_returns_explicit_match_for_current_draft_base() -> None:
    workflow = MutableWorkflow('source-b')
    coordinator = _coordinator_for(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    result = coordinator.verify_source(
        'tools',
        principal,
        draft_revision='draft-1',
        base_source_revision='source-b',
    )

    assert isinstance(result, SourceVerificationResult)
    assert result.draft_revision == 'draft-1'
    assert result.base_source_revision == 'source-b'
    assert result.source_revision == 'source-b'
    assert result.source_audit.actor == 'Admin'
    assert result.matches is True


def test_verify_source_returns_explicit_conflict_without_writing() -> None:
    workflow = MutableWorkflow('source-b')
    coordinator = _coordinator_for(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    result = coordinator.verify_source(
        'tools',
        principal,
        draft_revision='draft-1',
        base_source_revision='source-a',
    )

    assert result.matches is False
    assert result.base_source_revision == 'source-a'
    assert result.source_revision == 'source-b'
    assert workflow.published_expected is None


def test_missing_source_can_be_recreated_after_verification() -> None:
    workflow = MutableWorkflow(None)
    coordinator = _coordinator_for(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    payload = {'value': 'draft'}

    verification = coordinator.verify_source(
        'tools',
        principal,
        draft_revision=build_draft_revision(payload),
        base_source_revision='source-a',
    )
    publication = coordinator.publish_draft(
        'tools',
        principal,
        payload,
        verification.source_revision,
    )

    assert verification.source_revision is None
    assert verification.publishable is True
    assert verification.conflict is False
    assert publication.published is True
