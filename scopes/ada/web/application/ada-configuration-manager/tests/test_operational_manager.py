from __future__ import annotations

from types import SimpleNamespace

from dash import no_update

from ada.web.application.configuration_manager.operational import (
    OperationalAssignmentContext,
    OperationalCatalogManagerWebContext,
    _position_options,
    create_operational_manager_module,
    register_operational_callbacks,
)
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE,
    OPERATIONAL_CATALOG_PROJECTION_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_READER_SERVICE,
    OPERATIONAL_CATALOG_SOURCE_SERVICE,
    compose_operational_catalog_manager_contracts,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
    assignment_source_key,
)
from atlanticus.web.manager import ManagerPrincipal, ManagerWorkspaceBinding
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_result_id,
    workflow_saved_draft_id,
)
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore

USER_ID = 'user:' + 'a' * 24
MODULE_KEY = 'operational-identification'


class MemoryProjectionStore(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class FakeUsers:
    def get(self, user_id):
        return SimpleNamespace(user_id=user_id) if user_id == USER_ID else None


class FakeApp:
    def __init__(self):
        self.registered = {}

    def callback(self, *args, **kwargs):
        def decorator(fn):
            self.registered[fn.__name__] = fn
            return fn

        return decorator


def _contexts(tmp_path, *, allowed=True):
    store = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = MemoryProjectionStore()
    service = OperationalIdentificationService(
        source_store=store,
        projections=projection,
        users=FakeUsers(),
    )

    def principal() -> ManagerPrincipal:
        return ManagerPrincipal(
            subject_id='operator',
            display_name='Operator',
            profile_keys=('basic',),
            access_keys=('operational.manage',) if allowed else (),
        )

    contracts = compose_operational_catalog_manager_contracts(
        service=service,
        source_store=store,
        projection_store=projection,
        audit_actor_provider=lambda: principal().subject_id,
    )
    workspace = ManagerWorkspaceBinding(
        owner_subject_id_provider=lambda: principal().subject_id,
        source_key=contracts.source.source_key,
        source_snapshot_provider=contracts.source.get_source_snapshot,
    )
    catalog_context = OperationalCatalogManagerWebContext(
        editor=contracts.editor,
        current_payload_provider=lambda: contracts.source.load_current_source().payload,
        workspace_payload_reader=workspace.load_payload,
        workspace_payload_writer=workspace.save_payload,
        draft_store_id=workflow_draft_id(MODULE_KEY),
        saved_draft_store_id=workflow_saved_draft_id(MODULE_KEY),
        draft_save_action_id=workflow_action_id(MODULE_KEY, 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id(MODULE_KEY),
        result_id=workflow_result_id(MODULE_KEY),
        can_manage=lambda: 'operational.manage' in principal().access_keys,
    )
    assignment_context = OperationalAssignmentContext(
        service=service,
        promoted_users=lambda: (SimpleNamespace(user_id=USER_ID, display_name='Operator'),),
        principal=principal,
    )
    return catalog_context, assignment_context, contracts, service


def test_catalog_options_distinguish_inactive_entries():
    catalog = OperationalCatalog(positions=(Position('engineering', 'Engineering', active=False),))
    assert _position_options(catalog)[0]['disabled'] is True
    assert _position_options(catalog, include_inactive=True)[0]['disabled'] is False


def test_operational_manager_is_standard_module_with_assignments_companion(tmp_path):
    catalog_context, assignment_context, _contracts, _service = _contexts(tmp_path)
    module = create_operational_manager_module(
        catalog_context=catalog_context,
        assignment_context=assignment_context,
        source_name='Operational Source',
        projection_name='Operational Projection',
    )
    assert module.key == MODULE_KEY
    assert module.route == '/operational-identification'
    assert module.group_key == 'administration'
    assert module.access_key == 'operational.manage'
    assert module.source_key == CATALOG_SOURCE_KEY
    assert module.source_service == OPERATIONAL_CATALOG_SOURCE_SERVICE
    assert module.source_reader_service == OPERATIONAL_CATALOG_SOURCE_READER_SERVICE
    assert module.source_history_service == OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE
    assert module.projection_service == OPERATIONAL_CATALOG_PROJECTION_SERVICE
    assert module.draft_validation_service == OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE
    assert module.companion_view is not None
    assert module.companion_view.title == 'Asignaciones'
    assert module.primary_view_title == 'Catálogo de cargos'
    assert module.default_primary_view == 'companion'
    assert module.source_name == 'Operational Source'
    assert module.projection_name == 'Operational Projection'


def test_catalog_editor_updates_browser_draft_without_publishing_source(tmp_path):
    catalog_context, assignment_context, _contracts, service = _contexts(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    initial = OperationalCatalog().to_document()
    updated, options, position_id, result = app.registered['apply_position'](
        1,
        None,
        'Engineer',
        ['active'],
        initial,
    )
    assert position_id.startswith('position_')
    assert options[0]['value'] == position_id
    assert result is not None
    assert service.catalog_for_edit()[0].current is None
    assert service.catalog_for_read().positions == ()

    revision = app.registered['track_catalog_revision'](updated)
    _, save_result, draft, saved = app.registered['save_catalog_draft'](
        1,
        None,
        updated,
        None,
        revision,
    )
    assert save_result is not None
    assert draft == saved
    assert draft['payload']['positions'][0]['id'] == position_id
    assert service.catalog_for_edit()[0].current is None
    assert service.catalog_for_read().positions == ()


def test_catalog_publication_and_projection_remain_standard_manager_workflow(tmp_path):
    catalog_context, _assignment_context, contracts, service = _contexts(tmp_path)
    payload, position_id = catalog_context.editor.add_position(
        OperationalCatalog().to_document(),
        label='Engineer',
    )
    validation = contracts.validation.validate_draft(payload)
    assert validation.valid is True
    published = contracts.source.publish_draft(payload, contracts.source.get_source_snapshot())
    assert published.source.snapshot.current is not None
    assert service.catalog_for_read().positions == ()
    target = contracts.projection.select_current_target(CATALOG_SOURCE_KEY)
    assert target is not None
    contracts.projection.project(target)
    assert service.catalog_for_read().position(position_id) is not None


def test_assignment_remains_immediate_and_uses_individual_source(tmp_path):
    _catalog_context, assignment_context, contracts, service = _contexts(tmp_path)
    payload, position_id = contracts.editor.add_position(
        OperationalCatalog().to_document(),
        label='Engineer',
    )
    contracts.source.publish_draft(payload, contracts.source.get_source_snapshot())
    target = contracts.projection.select_current_target(CATALOG_SOURCE_KEY)
    assert target is not None
    contracts.projection.project(target)

    app = FakeApp()
    register_operational_callbacks(app, _catalog_context, assignment_context)
    _, _, _, revision = app.registered['select_user'](USER_ID)
    updated_revision, result = app.registered['save_assignment'](
        1,
        USER_ID,
        'mina',
        position_id,
        2,
        revision,
    )
    assert result is not None
    assert updated_revision is not None
    assert service.assignment_for_read(USER_ID).area_id == 'mina'
    assert service.assignment_for_read(USER_ID).position_id == position_id
    assert service.assignment_for_read(USER_ID).group_id == 2
    status = service.projection_status(assignment_source_key(USER_ID))
    assert status.projected_source_release is not None



def test_catalog_draft_rejects_stale_editor_revision(tmp_path):
    catalog_context, assignment_context, _contracts, service = _contexts(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    updated, _options, _position_id, _result = app.registered['apply_position'](
        1,
        None,
        'Engineer',
        ['active'],
        OperationalCatalog().to_document(),
    )
    workflow_result, local_result, draft, saved = app.registered['save_catalog_draft'](
        1,
        None,
        updated,
        None,
        'stale-revision',
    )
    assert workflow_result is not None
    assert local_result is not None
    assert draft is no_update
    assert saved is no_update
    assert service.catalog_for_edit()[0].current is None


def test_assignment_callback_rejects_stale_source_revision(tmp_path):
    catalog_context, assignment_context, _contracts, service = _contexts(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    snapshot, current = service.assignment_for_edit(USER_ID)
    service.publish_assignment(
        current,
        actor='operator',
        expected=snapshot,
    )
    revision, result = app.registered['save_assignment'](
        1,
        USER_ID,
        'mina',
        None,
        1,
        None,
    )
    assert revision is no_update
    assert result is not None
    assert service.assignment_for_read(USER_ID).area_id is None

def test_assignment_callbacks_enforce_permission(tmp_path):
    catalog_context, assignment_context, _contracts, service = _contexts(tmp_path, allowed=False)
    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    result = app.registered['save_assignment'](1, USER_ID, 'mina', None, 1, None)
    assert result[0] is no_update
    assert service.assignment_for_read(USER_ID).area_id is None


def test_manager_does_not_assign_unknown_user(tmp_path):
    catalog_context, assignment_context, _contracts, _service = _contexts(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    unknown = 'user:' + 'b' * 24
    revision, result = app.registered['save_assignment'](
        1,
        unknown,
        'mina',
        None,
        1,
        None,
    )
    assert revision is no_update
    assert result is not None
