from __future__ import annotations

from types import SimpleNamespace

import dash_bootstrap_components as dbc

from ada.web.application.configuration_manager import operational_ids as ids
from ada.web.application.configuration_manager.operational import (
    OperationalAssignmentContext,
    OperationalCatalogManagerWebContext,
)
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    compose_operational_catalog_manager_contracts,
)
from ada.web.application.configuration_manager.operational_layout import (
    build_operational_assignments,
    build_operational_catalog_configuration,
)
from ada.web.application.configuration_manager.workspace import ManagerWorkspaceBridge
from ada.web.operational.identification import OperationalIdentificationService
from atlanticus.web.manager import ManagerPrincipal
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


class _Projection(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class _Users:
    def get(self, user_id):
        return None


def _find(component, target):
    if getattr(component, 'id', None) == target:
        return component
    children = getattr(component, 'children', None)
    if not isinstance(children, (tuple, list)):
        children = () if children is None else (children,)
    return next((found for child in children if (found := _find(child, target)) is not None), None)


def _contexts(tmp_path):
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = _Projection()
    service = OperationalIdentificationService(
        source_store=source,
        projections=projection,
        users=_Users(),
    )

    def principal() -> ManagerPrincipal:
        return ManagerPrincipal(
            subject_id='operator',
            display_name='Operator',
            profile_keys=('basic',),
            access_keys=('operational.manage',),
        )

    contracts = compose_operational_catalog_manager_contracts(
        service=service,
        source_store=source,
        projection_store=projection,
        audit_actor_provider=lambda: 'operator',
    )
    bridge = ManagerWorkspaceBridge(
        owner_subject_id_provider=lambda: 'operator',
        source_snapshot_provider=contracts.source.get_source_snapshot,
    )
    catalog = OperationalCatalogManagerWebContext(
        editor=contracts.editor,
        current_payload_provider=lambda: contracts.source.load_current_source().payload,
        workspace_payload_reader=bridge.read_payload,
        workspace_payload_writer=bridge.write_payload,
        draft_store_id=workflow_draft_id(MODULE_KEY),
        saved_draft_store_id=workflow_saved_draft_id(MODULE_KEY),
        draft_save_action_id=workflow_action_id(MODULE_KEY, 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id(MODULE_KEY),
        result_id=workflow_result_id(MODULE_KEY),
        can_manage=lambda: True,
    )
    assignments = OperationalAssignmentContext(
        service=service,
        promoted_users=lambda: (SimpleNamespace(user_id='user:1', display_name='User'),),
        principal=principal,
    )
    return catalog, assignments


def test_catalog_and_assignment_surfaces_keep_independent_controls(tmp_path):
    catalog_context, assignment_context = _contexts(tmp_path)
    catalog = build_operational_catalog_configuration(catalog_context)
    assignments = build_operational_assignments(assignment_context)

    assert _find(catalog, ids.POSITION_LIST) is not None
    assert _find(catalog, ids.POSITION_SIZE) is not None
    assert _find(catalog, ids.CATALOG_EDITOR) is not None
    assert _find(catalog, ids.CATALOG_SAVE_DRAFT) is not None
    assert _find(catalog, ids.ASSIGN_LIST) is None
    assert isinstance(_find(catalog, ids.POSITION_ACTIVE), dbc.Checklist)

    assert _find(assignments, ids.ASSIGN_LIST) is not None
    assert _find(assignments, ids.ASSIGN_SIZE) is not None
    assert _find(assignments, ids.ASSIGNMENT_REPROJECT) is not None
    assert _find(assignments, ids.POSITION_LIST) is None
