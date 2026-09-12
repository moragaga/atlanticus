from datetime import UTC, datetime
from types import SimpleNamespace

from dash import MATCH, Input

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    DraftValidationResult,
    ManagerDraft,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
    ProjectionAuditRecord,
    ProjectionExecutionResult,
    ProjectionStatus,
    RevisionHistoryEntry,
    SourcePublicationResult,
    SourceVerificationResult,
    build_draft_revision,
)
from atlanticus.web.manager.web import callbacks as manager_callbacks
from atlanticus.web.manager.web.ids import workflow_action_id
from atlanticus.web.services import ServiceRegistry


class _RecordedCallback:
    def __init__(self, dependencies, options, function) -> None:
        self.dependencies = dependencies
        self.options = options
        self.function = function


class _RecorderApp:
    def __init__(self) -> None:
        self.callbacks: list[_RecordedCallback] = []

    def callback(self, *dependencies, **options):
        def register(function):
            self.callbacks.append(_RecordedCallback(dependencies, options, function))
            return function

        return register


class _Workflow:
    def __init__(self) -> None:
        self.audit = ProjectionAuditRecord(
            actor='Admin',
            occurred_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        )
        self.status = ProjectionStatus('source-a', self.audit)
        self.validated: list[dict[str, object]] = []
        self.published: list[tuple[dict[str, object], str | None]] = []
        self.projected: list[str] = []
        self.loaded_revisions: list[str] = []
        self.payloads = {
            'source-a': {'value': 'source'},
            'history-a': {'value': 'history'},
        }

    def get_status(self) -> ProjectionStatus:
        return self.status

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        self.validated.append(dict(payload))
        return DraftValidationResult(build_draft_revision(payload), True, self.audit)

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        self.published.append((dict(payload), expected_source_revision))
        return SourcePublicationResult(build_draft_revision(payload), True, self.audit)

    def project(self, expected_source_revision: str) -> ProjectionExecutionResult:
        self.projected.append(expected_source_revision)
        return ProjectionExecutionResult(
            source_revision=expected_source_revision,
            projection_revision='projection-1',
            projected=True,
            audit=self.audit,
        )

    def load_revision(self, revision: str) -> dict[str, object]:
        self.loaded_revisions.append(revision)
        return dict(self.payloads[revision])

    def list_history(self, *, limit: int = 20) -> tuple[RevisionHistoryEntry, ...]:
        return (
            RevisionHistoryEntry(
                revision='history-a',
                saved_by='Admin',
                saved_at=self.audit.occurred_at,
            ),
        )[:limit]


def _registered_manager() -> tuple[_RecorderApp, _Workflow, ManagerPrincipal]:
    app = _RecorderApp()
    workflow = _Workflow()
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    group = ManagerModuleGroup('configuration', 'Configuraciones', 10)
    module = ManagerModule(
        key='tools',
        group_key=group.key,
        title='Herramientas',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        workflow_service='tools.workflow',
        source_name='Source',
        projection_name='Projection',
        force_publish_enabled=True,
    )
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    services = ServiceRegistry()
    services.add(module.workflow_service, workflow)

    manager_callbacks.register_manager_callbacks(
        app,
        definition=definition,
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )
    return app, workflow, principal


def _callback_for_action(app: _RecorderApp, action: str):
    target = workflow_action_id(MATCH, action)
    matches = [
        callback
        for callback in app.callbacks
        if any(
            isinstance(dependency, Input)
            and dependency.component_id == target
            and dependency.component_property == 'n_clicks'
            for dependency in callback.dependencies
        )
    ]
    assert len(matches) == 1
    return matches[0].function


def _trigger(monkeypatch, action: str) -> None:
    monkeypatch.setattr(
        manager_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=workflow_action_id('tools', action)),
    )


def _draft(principal: ManagerPrincipal) -> ManagerDraft:
    return ManagerDraft.create(
        owner_subject_id=principal.subject_id,
        payload={'value': 'draft'},
        base_source_revision='source-a',
        saved_at=datetime(2026, 9, 11, 12, 5, tzinfo=UTC),
    )


def _verification(
    draft: ManagerDraft,
    workflow: _Workflow,
    source_revision: str,
) -> SourceVerificationResult:
    return SourceVerificationResult(
        draft_revision=draft.revision,
        base_source_revision=draft.base_source_revision,
        source_revision=source_revision,
        source_audit=workflow.audit,
        checked_at=datetime(2026, 9, 11, 12, 6, tzinfo=UTC),
    )


def test_validation_validates_current_draft_without_remote_writes(monkeypatch) -> None:
    app, workflow, principal = _registered_manager()
    draft = _draft(principal)
    callback = _callback_for_action(app, 'validate')
    _trigger(monkeypatch, 'validate')

    message, validation, verification = callback(
        1,
        draft.to_document(),
        draft.revision,
    )

    assert message is None
    assert validation['draft_revision'] == draft.revision
    assert validation['valid'] is True
    assert verification is None
    assert workflow.validated == [draft.payload]
    assert workflow.published == []
    assert workflow.projected == []


def test_publication_persists_verified_draft_without_automatic_projection(monkeypatch) -> None:
    app, workflow, principal = _registered_manager()
    draft = _draft(principal)
    callback = _callback_for_action(app, 'publish')
    _trigger(monkeypatch, 'publish')
    validation = {'draft_revision': draft.revision, 'valid': True}
    verification = _verification(draft, workflow, 'source-a')

    result = callback(
        1,
        draft.to_document(),
        validation,
        verification.to_document(),
        draft.revision,
        4,
    )

    updated = ManagerDraft.from_document(result[2])
    assert result[0] is None
    assert result[1] == 5
    assert result[3] is None
    assert result[4] is None
    assert updated.base_source_revision == draft.revision
    assert workflow.published == [(draft.payload, 'source-a')]
    assert workflow.projected == []


def test_projection_is_an_explicit_action_using_the_current_source_revision(monkeypatch) -> None:
    app, workflow, _principal = _registered_manager()
    callback = _callback_for_action(app, 'project')
    _trigger(monkeypatch, 'project')

    message, refresh_signal, projection_signal = callback(
        1,
        {'source_revision': 'source-a'},
        2,
    )

    assert message is None
    assert refresh_signal == 3
    assert projection_signal == {
        'source_revision': 'source-a',
        'projection_revision': 'projection-1',
    }
    assert workflow.projected == ['source-a']
    assert workflow.published == []


def test_reload_reads_current_source_without_publishing_or_projecting(monkeypatch) -> None:
    app, workflow, _principal = _registered_manager()
    callback = _callback_for_action(app, 'reload')
    _trigger(monkeypatch, 'reload')

    result = callback(
        0,
        1,
        0,
        0,
        None,
        None,
        None,
        0,
        0,
    )

    reloaded = ManagerDraft.from_document(result[5])
    assert reloaded.payload == {'value': 'source'}
    assert reloaded.base_source_revision == 'source-a'
    assert result[9] == 1
    assert workflow.loaded_revisions == ['source-a']
    assert workflow.published == []
    assert workflow.projected == []


def test_keep_draft_rebases_local_work_without_writing_remote_state(monkeypatch) -> None:
    app, workflow, principal = _registered_manager()
    draft = _draft(principal)
    callback = _callback_for_action(app, 'keep-draft')
    _trigger(monkeypatch, 'keep-draft')
    verification = _verification(draft, workflow, 'source-b')

    result = callback(
        0,
        1,
        draft.to_document(),
        verification.to_document(),
        0,
    )

    rebased = ManagerDraft.from_document(result[1])
    assert rebased.revision == draft.revision
    assert rebased.base_source_revision == 'source-b'
    assert result[3] is None
    assert workflow.published == []
    assert workflow.projected == []
