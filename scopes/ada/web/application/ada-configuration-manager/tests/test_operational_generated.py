from __future__ import annotations

from dash import no_update

from ada.web.application.configuration_manager.operational import (
    OperationalAssignmentContext,
    OperationalCatalogManagerWebContext,
    register_operational_callbacks,
)
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    compose_operational_catalog_manager_contracts,
)
from ada.web.operational.identification import OperationalCatalog, OperationalIdentificationService
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

MODULE_KEY = 'operational-identification'


class MemoryProjection(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class NoUsers:
    def get(self, user_id):
        return None


class FakeApp:
    def __init__(self):
        self.registered = {}

    def callback(self, *_args, **_kwargs):
        def decorator(fn):
            self.registered[fn.__name__] = fn
            return fn

        return decorator


def _contexts(tmp_path):
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = MemoryProjection()
    service = OperationalIdentificationService(
        source_store=source,
        projections=projection,
        users=NoUsers(),
    )

    def principal() -> ManagerPrincipal:
        return ManagerPrincipal(
            subject_id='admin',
            display_name='Admin',
            profile_keys=('basic',),
            access_keys=('operational.manage',),
        )

    contracts = compose_operational_catalog_manager_contracts(
        service=service,
        source_store=source,
        projection_store=projection,
        audit_actor_provider=lambda: 'admin',
    )
    bridge = ManagerWorkspaceBinding(
        owner_subject_id_provider=lambda: 'admin',
        source_key=contracts.source.source_key,
        source_snapshot_provider=contracts.source.get_source_snapshot,
    )
    catalog = OperationalCatalogManagerWebContext(
        editor=contracts.editor,
        current_payload_provider=lambda: contracts.source.load_current_source().payload,
        workspace_payload_reader=bridge.load_payload,
        workspace_payload_writer=bridge.save_payload,
        draft_store_id=workflow_draft_id(MODULE_KEY),
        saved_draft_store_id=workflow_saved_draft_id(MODULE_KEY),
        draft_save_action_id=workflow_action_id(MODULE_KEY, 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id(MODULE_KEY),
        result_id=workflow_result_id(MODULE_KEY),
        can_manage=lambda: True,
    )
    assignments = OperationalAssignmentContext(
        service=service,
        promoted_users=lambda: (),
        principal=principal,
    )
    return catalog, assignments, service


def test_manager_creates_position_ids_server_side_and_reuses_them_in_draft(tmp_path):
    catalog_context, assignment_context, service = _contexts(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    initial = OperationalCatalog().to_document()

    created = app.registered['apply_position'](1, None, 'Operador', ['active'], initial)
    document, _options, identifier, _message = created
    assert identifier.startswith('position_')
    assert service.catalog_for_edit()[0].current is None

    edited = app.registered['apply_position'](
        2,
        identifier,
        'Operador de sala',
        ['active'],
        document,
    )
    edited_document, _options, edited_identifier, _message = edited
    assert edited_identifier == identifier
    assert OperationalCatalog.from_document(edited_document).position(identifier).label == (
        'Operador de sala'
    )
    assert service.catalog_for_edit()[0].current is None

    changed = app.registered['apply_position'](
        3,
        'tampered_id',
        'Inválido',
        ['active'],
        edited_document,
    )
    assert changed[0] is no_update
    assert OperationalCatalog.from_document(edited_document).position(identifier).label == (
        'Operador de sala'
    )
