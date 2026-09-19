from datetime import UTC, datetime

from dash import dcc

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_history_preview_id,
    workflow_history_preview_store_id,
    workflow_saved_draft_id,
    workflow_source_verification_id,
    workflow_validation_id,
)
from atlanticus.web.manager.web.layout import build_manager_surface, build_workflow_panel
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def _module() -> ManagerModule:
    return ManagerModule(
        key='tools',
        group_key='configuration',
        title='Herramientas',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        source_key=SourceKey('tools'),
        source_service='tools.source',
        source_reader_service='tools.reader',
        source_history_service='tools.history',
        projection_service='tools.projection',
        draft_validation_service='tools.validation',
        access_key='tools.manage',
        source_name='Source',
        projection_name='Projection',
    )


def _component_by_id(component: object, component_id: object) -> object | None:
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is None:
                continue
            found = _component_by_id(child, component_id)
            if found is not None:
                return found
    elif children is not None and not isinstance(children, str):
        return _component_by_id(children, component_id)
    return None


def test_manager_surface_keeps_browser_workspace_persistence_explicit() -> None:
    module = _module()
    group = ManagerModuleGroup('configuration', 'Configuraciones', 10)
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: ManagerPrincipal(
            'local',
            'Administrador local',
            access_keys=('tools.manage',),
            is_local=True,
        ),
        groups=(group,),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    surface = build_manager_surface(
        definition=definition,
        registry=registry,
        services=ServiceRegistry(),
        principal=definition.principal_provider(),
        authorization=DefaultManagerAuthorizationPolicy(),
    )

    transient_ids = (
        workflow_draft_id(module.key),
        workflow_validation_id(module.key),
        workflow_source_verification_id(module.key),
        workflow_editor_revision_id(module.key),
    )
    for component_id in transient_ids:
        store = _component_by_id(surface, component_id)
        assert isinstance(store, dcc.Store)
        assert store.storage_type == 'memory'

    saved_workspace = _component_by_id(surface, workflow_saved_draft_id(module.key))
    assert isinstance(saved_workspace, dcc.Store)
    assert saved_workspace.storage_type == 'local'


def test_workflow_panel_exposes_publication_and_projection_actions() -> None:
    module = _module()
    release = SourceReleaseRef(
        SourceReleaseId('release-1'),
        datetime(2026, 9, 15, 18, 0, tzinfo=UTC),
    )
    panel = build_workflow_panel(
        module=module,
        status=ProjectionStatus(
            alignment=ProjectionAlignment.NEVER_PROJECTED,
            source_current_release=release,
            projected_source_release=None,
        ),
        history=None,
        error=None,
    )

    expected_actions = (
        'discard-local',
        'reload',
        'recover-saved-draft',
        'discard-saved-draft',
        'save-draft',
        'validate',
        'verify-source',
        'publish',
        'project',
        'update-source',
        'keep-draft',
    )
    for action in expected_actions:
        assert _component_by_id(panel, workflow_action_id(module.key, action)) is not None


def test_history_preview_has_state_separate_from_browser_workspace() -> None:
    module = _module()
    panel = build_workflow_panel(module=module, status=None, history=None, error=None)

    preview = _component_by_id(panel, workflow_history_preview_id(module.key))
    preview_store = _component_by_id(panel, workflow_history_preview_store_id(module.key))

    assert preview is not None
    assert isinstance(preview_store, dcc.Store)
    assert preview_store.id != workflow_draft_id(module.key)
