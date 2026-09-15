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
    ProjectionStatus,
    build_workspace_revision,
)
from atlanticus.web.manager.web import callbacks as manager_callbacks
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_history_preview_load_id,
)
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace
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
    def __init__(self, dependencies, function) -> None:
        self.dependencies = dependencies
        self.function = function


class _RecorderApp:
    def __init__(self) -> None:
        self.callbacks: list[_RecordedCallback] = []

    def callback(self, *dependencies, **_options):
        def register(function):
            self.callbacks.append(_RecordedCallback(dependencies, function))
            return function

        return register


def _snapshot(release_id: str, token: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 15, 17, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', f'hash-{release_id}'),
        ),
        concurrency_token=ConcurrencyToken(token),
    )


class _LegacyWorkflow:
    def get_status(self):
        return ProjectionStatus()

    def get_current_projection_target(self):
        return None

    def validate_draft(self, payload):
        raise AssertionError('legacy path must not be used')

    def publish_draft(self, payload, expected_source_revision):
        raise AssertionError('legacy path must not be used')

    def project(self, target):
        raise AssertionError('legacy path must not be used')


class _Validator:
    def validate_draft(self, payload):
        return DraftValidationResult(
            draft_revision=build_workspace_revision(payload),
            valid=True,
            audit=ProjectionAuditRecord(
                actor='Validator',
                occurred_at=datetime(2026, 9, 15, 17, 1, tzinfo=UTC),
            ),
        )


class _Exact:
    def __init__(self) -> None:
        self.snapshot = _snapshot('release-1', 'etag-1')
        self.payload = {'value': 'source'}

    def get_source_snapshot(self):
        return self.snapshot

    def load_current_source_exact(self):
        return ExactSourceReadResult(
            snapshot=self.snapshot,
            payload=dict(self.payload),
        )

    def publish_draft_exact(self, payload, expected_source_snapshot):
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


def _registered():
    app = _RecorderApp()
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    exact = _Exact()
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
        exact_source_reader_service='users.exact',
    )
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    services = ServiceRegistry()
    services.add('users.legacy', _LegacyWorkflow())
    services.add('users.validation', _Validator())
    services.add('users.exact', exact)
    manager_callbacks.register_manager_callbacks(
        app,
        definition=definition,
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )
    return app, principal, exact


def _workspace(principal, *, payload=None, base=None):
    workspace = ManagerWorkspace.create(
        owner_subject_id=principal.subject_id,
        payload=payload or {'value': 'draft'},
        base=base or _snapshot('release-1', 'etag-1'),
        saved_at_utc=datetime(2026, 9, 15, 17, 2, tzinfo=UTC),
    )
    document = workspace.to_document()
    document['document_type'] = 'users_domain_workspace'
    document['domain_metadata'] = {'preserve': True}
    return document


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


def _history_callback(app):
    target = workflow_history_preview_load_id(MATCH)
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


def test_recover_saved_exact_workspace_preserves_domain_document(monkeypatch) -> None:
    app, principal, _exact = _registered()
    document = _workspace(principal)
    workspace = ManagerWorkspace.from_document(document)
    callback = _callback_for_action(app, 'recover-saved-draft')
    _trigger(monkeypatch, 'recover-saved-draft')

    result = callback(1, 0, document, None)

    assert result[1] == document
    assert result[3] is None
    assert result[4] is None
    assert result[5] == workspace.revision


def test_update_source_replaces_payload_without_losing_domain_metadata(monkeypatch) -> None:
    app, principal, exact = _registered()
    document = _workspace(principal, payload={'value': 'local'})
    callback = _callback_for_action(app, 'update-source')
    _trigger(monkeypatch, 'update-source')

    result = callback(1, 0, document, None, 4)

    updated = ManagerWorkspace.from_document(result[1])
    assert updated.payload == {'value': 'source'}
    assert updated.base == exact.snapshot
    assert result[1]['document_type'] == 'users_domain_workspace'
    assert result[1]['domain_metadata'] == {'preserve': True}
    assert result[4] == 5


def test_keep_draft_rebases_exact_workspace_but_remains_local_work(monkeypatch) -> None:
    app, principal, exact = _registered()
    document = _workspace(principal, payload={'value': 'local'})
    workspace = ManagerWorkspace.from_document(document)
    current = _snapshot('release-2', 'etag-2')
    exact.snapshot = current
    exact.payload = {'value': 'remote'}
    verification = ManagerSourceVerification(
        workspace_revision=workspace.revision,
        base=workspace.base,
        source=current,
        checked_at_utc=datetime(2026, 9, 15, 17, 3, tzinfo=UTC),
    )
    callback = _callback_for_action(app, 'keep-draft')
    _trigger(monkeypatch, 'keep-draft')

    result = callback(0, 1, document, verification.to_document(), 2)

    rebased_document = result[1]
    rebased = ManagerWorkspace.from_document(rebased_document)
    assert rebased.payload == workspace.payload
    assert rebased.base == current
    assert rebased.has_local_changes is False
    assert rebased_document['domain_metadata'] == {'preserve': True}

    reload_callback = _callback_for_action(app, 'reload')
    _trigger(monkeypatch, 'reload')
    reload_result = reload_callback(
        0,
        1,
        0,
        0,
        rebased_document,
        rebased.revision,
        None,
        0,
        0,
    )

    assert reload_result[0] is False
    assert reload_result[3] == 'reload'
    assert reload_result[5] is manager_callbacks.no_update


def test_reload_exact_workspace_after_confirmation_restores_source(monkeypatch) -> None:
    app, principal, exact = _registered()
    exact.payload = {'value': 'remote'}
    document = _workspace(principal, payload={'value': 'local'})
    callback = _callback_for_action(app, 'workspace-confirm')
    _trigger(monkeypatch, 'workspace-confirm')

    result = callback(
        0,
        0,
        1,
        0,
        document,
        ManagerWorkspace.from_document(document).revision,
        'reload',
        0,
        0,
    )

    restored = ManagerWorkspace.from_document(result[5])
    assert restored.payload == exact.payload
    assert restored.base == exact.snapshot
    assert result[5]['domain_metadata'] == {'preserve': True}
    assert result[9] == 1


def test_history_as_draft_is_blocked_for_exact_source_module(monkeypatch) -> None:
    app, _principal, _exact = _registered()
    callback = _history_callback(app)
    monkeypatch.setattr(
        manager_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=workflow_history_preview_load_id('users')),
    )

    result = callback(
        1,
        {
            'schema_version': 1,
            'module_key': 'users',
            'revision': 'legacy-revision',
            'payload': {'value': 'history'},
        },
        None,
    )

    assert result[1:] == (
        manager_callbacks.no_update,
        manager_callbacks.no_update,
        manager_callbacks.no_update,
        manager_callbacks.no_update,
        manager_callbacks.no_update,
    )
