from datetime import UTC, datetime

from dash import Dash

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    DraftValidationResult,
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
    build_draft_revision,
)
from atlanticus.web.manager.web.callbacks import register_manager_callbacks
from atlanticus.web.services import ServiceRegistry


class _Workflow:
    def __init__(self) -> None:
        self.audit = ProjectionAuditRecord(
            actor='Admin',
            occurred_at=datetime(2026, 8, 22, 0, 0, tzinfo=UTC),
        )

    def get_status(self) -> ProjectionStatus:
        return ProjectionStatus()

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        return DraftValidationResult(build_draft_revision(payload), True, self.audit)

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
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
        return ()


def test_manager_callbacks_register_with_real_dash_application() -> None:
    app = Dash(__name__)
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
        source_name='Archivo local',
        projection_name='Archivo local',
    )
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,),
        modules=(module,),
        default_module_key=module.key,
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    services = ServiceRegistry()
    services.add(module.workflow_service, _Workflow())

    register_manager_callbacks(
        app,
        definition=definition,
        registry=registry,
        services=services,
        authorization=DefaultManagerAuthorizationPolicy(),
    )

    assert app.callback_map
