from datetime import UTC, datetime
from types import SimpleNamespace

from dash import MATCH, Input

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerProjectionCoordinator,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.projection import ProjectionState, resolve_projection_state
from atlanticus.web.manager.web import callbacks as manager_callbacks
from atlanticus.web.manager.web.ids import workflow_action_id
from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionExecutionResult,
    ProjectionRecord,
    ProjectionStatus,
    ProjectionTarget,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import (
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
)


class _ExactProjection:
    def __init__(self) -> None:
        self.target = ProjectionTarget(
            source_key=SourceKey('users'),
            source_release=SourceReleaseRef(
                release_id=SourceReleaseId('release-1'),
                published_at_utc=datetime(2026, 9, 15, 18, 0, tzinfo=UTC),
            ),
        )
        self.projected: list[ProjectionTarget] = []
        self.status = ProjectionStatus(
            alignment=ProjectionAlignment.CURRENT,
            source_current_release=self.target.source_release,
            projected_source_release=self.target.source_release,
        )

    def get_status(self) -> ProjectionStatus:
        return self.status

    def get_current_projection_target(self) -> ProjectionTarget | None:
        return self.target

    def project(self, target: ProjectionTarget) -> ProjectionExecutionResult[object]:
        self.projected.append(target)
        return ProjectionExecutionResult(
            target=target,
            projection=ProjectionRecord(
                source_key=target.source_key,
                source_release_id=target.source_release_id,
                source_published_at_utc=target.source_release.published_at_utc,
                projected_at_utc=datetime(2026, 9, 15, 18, 1, tzinfo=UTC),
                payload={'users': []},
            ),
        )


def _module() -> ManagerModule:
    return ManagerModule(
        key='users',
        group_key='configuration',
        title='Usuarios',
        route='/users',
        order=10,
        layout=lambda _services: None,
        draft_validation_service='users.validation',
        exact_source_reader_service='users.reader',
        exact_source_workflow_service='users.source',
        exact_projection_service='users.projection',
    )


def _coordinator(service: object):
    module = _module()
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (module,),
    )
    services = ServiceRegistry()
    services.add('users.projection', service)
    return (
        ManagerProjectionCoordinator(
            registry=registry,
            services=services,
            authorization=DefaultManagerAuthorizationPolicy(),
        ),
        registry,
        services,
    )


def test_exact_projection_status_is_canonical_and_does_not_use_legacy_revision_fields() -> None:
    workflow = _ExactProjection()
    coordinator, _registry, _services = _coordinator(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    status = coordinator.get_status('users', principal)

    assert status is workflow.status
    assert status.alignment is ProjectionAlignment.CURRENT
    assert resolve_projection_state(status) is ProjectionState.SYNCHRONIZED
    assert not hasattr(status, 'source_revision')


def test_exact_projection_routes_without_legacy_lifecycle() -> None:
    workflow = _ExactProjection()
    coordinator, _registry, _services = _coordinator(workflow)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    target = coordinator.get_current_projection_target('users', principal)
    assert target == workflow.target
    assert target is not None

    result = coordinator.project('users', principal, target)

    assert result.target == target
    assert result.projection.source_release == target.source_release
    assert workflow.projected == [target]


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


def _project_callback(app):
    target = workflow_action_id(MATCH, 'project')
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


def test_exact_projection_callback_emits_only_canonical_projection_identity(monkeypatch) -> None:
    app = _RecorderApp()
    workflow = _ExactProjection()
    module = _module()
    group = ManagerModuleGroup('configuration', 'Configuraciones', 10)
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    services = ServiceRegistry()
    services.add('users.projection', workflow)
    manager_callbacks.register_manager_callbacks(
        app,
        definition=definition,
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )
    monkeypatch.setattr(
        manager_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=workflow_action_id('users', 'project')),
    )

    result = _project_callback(app)(1, 0)

    assert result[0] is None
    assert result[1] == 1
    assert result[2] == {
        'source_key': 'users',
        'source_release_id': 'release-1',
        'source_published_at_utc': '2026-09-15T18:00:00+00:00',
        'projected_at_utc': '2026-09-15T18:01:00+00:00',
    }
    assert 'projection_revision' not in result[2]
