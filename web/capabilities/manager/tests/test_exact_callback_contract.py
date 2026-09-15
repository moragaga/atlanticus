from datetime import UTC, datetime
from types import SimpleNamespace

from dash import MATCH, Input

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    DraftValidationResult,
    ExactSourcePublicationResult,
    ExactSourceReadResult,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
    ProjectionAuditRecord,
    ProjectionExecutionResult,
    ProjectionStatus,
    build_workspace_revision,
)
from atlanticus.web.manager.web import callbacks as manager_callbacks
from atlanticus.web.manager.web.ids import workflow_action_id
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace
from atlanticus.web.projection.models import ProjectionTarget
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


def _snapshot(release_id: str, token: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 15, 16, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', f'hash-{release_id}'),
        ),
        concurrency_token=ConcurrencyToken(token),
    )


class _LegacyWorkflow:
    def __init__(self) -> None:
        self.audit = ProjectionAuditRecord(
            actor='Legacy',
            occurred_at=datetime(2026, 9, 15, 16, 0, tzinfo=UTC),
        )
        self.published: list[object] = []

    def get_status(self):
        return ProjectionStatus()

    def get_current_projection_target(self):
        return None

    def validate_draft(self, payload):
        raise AssertionError('legacy validation must not be used')

    def publish_draft(self, payload, expected_source_revision):
        self.published.append((payload, expected_source_revision))
        raise AssertionError('legacy publication must not be used')

    def project(self, target):
        raise AssertionError('projection is outside this test')


class _Validator:
    def __init__(self) -> None:
        self.payloads = []

    def validate_draft(self, payload):
        self.payloads.append(dict(payload))
        return DraftValidationResult(
            draft_revision=build_workspace_revision(payload),
            valid=True,
            audit=ProjectionAuditRecord(
                actor='Validator',
                occurred_at=datetime(2026, 9, 15, 16, 1, tzinfo=UTC),
            ),
        )


class _Reader:
    def __init__(self, publisher) -> None:
        self.publisher = publisher

    def load_current_source_exact(self):
        return ExactSourceReadResult(
            snapshot=self.publisher.snapshot,
            payload=dict(self.publisher.source_payload),
        )


class _Publisher:
    def __init__(self) -> None:
        self.snapshot = _snapshot('release-1', 'etag-1')
        self.source_payload = {'value': 'source'}
        self.published = []

    def get_source_snapshot(self):
        return self.snapshot

    def publish_draft_exact(self, payload, expected_source_snapshot):
        self.published.append((dict(payload), expected_source_snapshot))
        self.snapshot = _snapshot('release-2', 'etag-2')
        self.source_payload = dict(payload)
        assert self.snapshot.current is not None
        release = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.snapshot.source_key,
            release_ref=self.snapshot.current.release_ref,
            content_hash=self.snapshot.current.content_hash,
            resources=(),
        )
        return ExactSourcePublicationResult(
            source=PublishResult(release=release, snapshot=self.snapshot),
            audit=ProjectionAuditRecord(
                actor='Publisher',
                occurred_at=self.snapshot.current.release_ref.published_at_utc,
            ),
        )


def _registered_manager():
    app = _RecorderApp()
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    legacy = _LegacyWorkflow()
    validator = _Validator()
    publisher = _Publisher()
    reader = _Reader(publisher)
    group = ManagerModuleGroup('configuration', 'Configuraciones', 10)
    module = ManagerModule(
        key='users',
        group_key=group.key,
        title='Usuarios',
        route='/users',
        order=10,
        layout=lambda _services: None,
        workflow_service='users.legacy',
        exact_source_workflow_service='users.exact',
        draft_validation_service='users.validation',
        exact_source_reader_service='users.reader',
    )
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    services = ServiceRegistry()
    services.add('users.legacy', legacy)
    services.add('users.validation', validator)
    services.add('users.exact', publisher)
    services.add('users.reader', reader)
    manager_callbacks.register_manager_callbacks(
        app,
        definition=definition,
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )
    return app, principal, legacy, validator, publisher


def _callback_for_action(app, action):
    target = workflow_action_id(MATCH, action)
    matches = [
        callback.function
        for callback in app.callbacks
        if any(
            isinstance(dependency, Input)
            and dependency.component_id == target
            and dependency.component_property == 'n_clicks'
            for dependency in callback.dependencies
        )
    ]
    assert len(matches) == 1
    return matches[0]


def _trigger(monkeypatch, action):
    monkeypatch.setattr(
        manager_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=workflow_action_id('users', action)),
    )


def _workspace_document(principal):
    workspace = ManagerWorkspace.create(
        owner_subject_id=principal.subject_id,
        payload={'value': 'draft'},
        base=_snapshot('release-1', 'etag-1'),
        saved_at_utc=datetime(2026, 9, 15, 16, 2, tzinfo=UTC),
    )
    document = workspace.to_document()
    document['document_type'] = 'users_domain_workspace'
    document['domain_metadata'] = {'preserve': 'yes'}
    return document


def test_exact_validation_uses_declared_validator_not_legacy_lifecycle(monkeypatch) -> None:
    app, principal, legacy, validator, publisher = _registered_manager()
    document = _workspace_document(principal)
    workspace = ManagerWorkspace.from_document(document)
    callback = _callback_for_action(app, 'validate')
    _trigger(monkeypatch, 'validate')

    message, validation, verification = callback(1, document, workspace.revision)

    assert message is None
    assert validation['draft_revision'] == workspace.revision
    assert verification is None
    assert validator.payloads == [workspace.payload]
    assert legacy.published == []
    assert publisher.published == []


def test_exact_verify_and_publish_preserve_domain_document_without_legacy_publication(
    monkeypatch,
) -> None:
    app, principal, legacy, validator, publisher = _registered_manager()
    document = _workspace_document(principal)
    workspace = ManagerWorkspace.from_document(document)
    validation = {'draft_revision': workspace.revision, 'valid': True}

    verify_callback = _callback_for_action(app, 'verify-source')
    _trigger(monkeypatch, 'verify-source')
    verify_result = verify_callback(
        1,
        document,
        validation,
        workspace.revision,
        0,
    )
    verification = ManagerSourceVerification.from_document(verify_result[1])
    assert verification.workspace_revision == workspace.revision
    assert verification.source == publisher.snapshot

    publish_callback = _callback_for_action(app, 'publish')
    _trigger(monkeypatch, 'publish')
    publish_result = publish_callback(
        1,
        document,
        validation,
        verification.to_document(),
        workspace.revision,
        0,
    )

    updated = publish_result[2]
    rebased = ManagerWorkspace.from_document(updated)
    assert publish_result[0] is None
    assert publish_result[1] == 1
    assert publish_result[3] is None
    assert publish_result[4] is None
    assert updated['document_type'] == 'users_domain_workspace'
    assert updated['domain_metadata'] == {'preserve': 'yes'}
    assert rebased.base == publisher.snapshot
    assert rebased.payload == workspace.payload
    assert legacy.published == []
    assert publisher.published == [(workspace.payload, verification.source)]
