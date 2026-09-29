from __future__ import annotations

from types import SimpleNamespace

from ada.web.application.configuration_manager.operational import OperationalManagerContext
from ada.web.application.configuration_manager.operational_layout import (
    build_operational_manager_layout,
)
from ada.web.operational.identification import OperationalIdentificationService
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


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


def test_configuration_and_trace_share_one_manager_shell_without_duplicate_title(tmp_path):
    from ada.web.application.configuration_manager import operational_ids as ids

    service = OperationalIdentificationService(
        source_store=LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source')),
        projections=_Projection(),
        users=_Users(),
    )
    context = OperationalManagerContext(
        service=service,
        promoted_users=lambda: (),
        principal=lambda: ManagerPrincipal(
            subject_id='operator',
            display_name='Operator',
            profile_keys=('basic',),
            access_keys=('operational.manage',),
        ),
        source_name='Blob Storage',
        projection_name='Cosmos DB',
    )
    layout = build_operational_manager_layout(context)
    assert _find(layout, ids.CONFIG_TAB) is not None
    assert _find(layout, ids.TRACE_TAB) is not None
    assert _find(layout, ids.CONFIG_PANEL) is not None
    assert _find(layout, ids.TRACE_PANEL) is not None
    assert _find(layout, ids.ASSIGN_SIZE) is not None
    assert _find(layout, ids.POSITION_SIZE) is not None
    assert _find(_find(layout, ids.ASSIGN_LIST), ids.ASSIGN_SIZE) is None
    assert _find(_find(layout, ids.POSITION_LIST), ids.POSITION_SIZE) is None
    assert _find(_find(layout, ids.POSITION_PANEL), ids.CATALOG_METADATA) is None
    assert _find(_find(layout, ids.TRACE_PANEL), ids.CATALOG_METADATA) is not None
