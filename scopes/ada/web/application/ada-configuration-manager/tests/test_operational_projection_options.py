from __future__ import annotations

from types import SimpleNamespace

from ada.web.application.configuration_manager import operational_ids as ids
from ada.web.application.configuration_manager.operational import (
    OperationalAssignmentContext,
    OperationalCatalogManagerWebContext,
    build_operational_assignments,
    build_operational_catalog_configuration,
    register_operational_callbacks,
)
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    compose_operational_catalog_manager_contracts,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
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


class ProjectionMemory(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class FakeMemberships:
    def load(self):
        return self

    def get(self, user_id):
        return SimpleNamespace(user_id=user_id) if user_id == USER_ID else None


class FakeApp:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *_args, **_kwargs):
        def register(callback):
            self.callbacks[callback.__name__] = callback
            return callback

        return register


def contexts_for(tmp_path):
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = ProjectionMemory()
    service = OperationalIdentificationService(
        source_store=source,
        projections=projection,
        memberships=FakeMemberships(),
    )

    def principal() -> ManagerPrincipal:
        return ManagerPrincipal(
            subject_id='admin',
            display_name='Administrador',
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
        promoted_users=lambda: (SimpleNamespace(user_id=USER_ID, display_name='Operador'),),
        principal=principal,
    )
    return catalog, assignments


def descendants(value):
    if isinstance(value, (tuple, list)):
        for item in value:
            yield from descendants(item)
    elif isinstance(value, str):
        yield value
    elif value is not None:
        yield value
        yield from descendants(getattr(value, 'children', None))


def test_assignments_display_only_projected_available_positions(tmp_path):
    catalog_context, assignment_context = contexts_for(tmp_path)
    snapshot, _ = assignment_context.service.catalog_for_edit()
    assignment_context.service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero'),)),
        actor='admin',
        expected=snapshot,
    )
    assignment_layout = build_operational_assignments(assignment_context)
    components = tuple(descendants(assignment_layout))
    position_control = next(
        item for item in components if getattr(item, 'id', None) == ids.POSITION
    )
    assert position_control.options == []

    catalog_layout = build_operational_catalog_configuration(catalog_context)
    catalog_components = tuple(descendants(catalog_layout))
    assert {'Áreas operacionales', 'Mina · Planta', 'Grupos', '1 · 2 · 3 · 4'}.issubset(
        {item for item in catalog_components if isinstance(item, str)}
    )

    app = FakeApp()
    register_operational_callbacks(app, catalog_context, assignment_context)
    assert app.callbacks['assignment_position_options'](USER_ID) == []
    assignment_context.service.project_current(CATALOG_SOURCE_KEY)
    assert app.callbacks['assignment_position_options'](USER_ID) == [
        {'label': 'Ingeniero', 'value': 'engineer', 'disabled': False},
    ]

    next_snapshot, _ = assignment_context.service.catalog_for_edit()
    assignment_context.service.publish_catalog(
        OperationalCatalog(
            (
                Position('engineer', 'Ingeniero'),
                Position('supervisor', 'Supervisor'),
            )
        ),
        actor='admin',
        expected=next_snapshot,
    )
    assert app.callbacks['assignment_position_options'](USER_ID) == [
        {'label': 'Ingeniero', 'value': 'engineer', 'disabled': True},
    ]
    assignment_context.service.project_current(CATALOG_SOURCE_KEY)
    assert all(
        not item['disabled'] for item in app.callbacks['assignment_position_options'](USER_ID)
    )
