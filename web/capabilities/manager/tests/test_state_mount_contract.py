from __future__ import annotations

import json

from dash import dcc

from atlanticus.web.manager import (
    ManagerModule,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurface,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web.ids import (
    LOCATION_ID,
    REFRESH_SIGNAL_ID,
    STATUS_STORE_ID,
    workflow_draft_id,
    workflow_saved_draft_id,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey


def _module(key: str, access_key: str) -> ManagerModule:
    return ManagerModule(
        key=key,
        group_key='configuration',
        title=key,
        route=f'/{key}',
        order=10,
        layout=lambda _services: None,
        source_key=SourceKey(key),
        source_service=f'{key}.source',
        source_reader_service=f'{key}.reader',
        source_history_service=f'{key}.history',
        projection_service=f'{key}.projection',
        draft_validation_service=f'{key}.validation',
        access_key=access_key,
        source_signal_id=f'{key}-source-updated',
    )


def _surface() -> ManagerSurface:
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: ManagerPrincipal(
            'local', 'Administrador local', access_keys=('tools.manage',), is_local=True
        ),
        groups=(ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        modules=(_module('tools', 'tools.manage'), _module('hidden', 'hidden.manage')),
    )
    return ManagerSurface(definition)


def _components(component: object):
    if isinstance(component, (tuple, list)):
        for item in component:
            yield from _components(item)
        return
    if component is None or isinstance(component, (str, int, float, bool)):
        return
    yield component
    yield from _components(getattr(component, 'children', None))


def _ids(component: object) -> list[str]:
    return [
        json.dumps(child.id, sort_keys=True)
        for child in _components(component)
        if getattr(child, 'id', None) is not None
    ]


def test_manager_state_survives_separate_visual_mount_without_duplicate_ids() -> None:
    surface = _surface()
    state_host = surface.state_layout()
    visual = surface.layout(ServiceRegistry(), include_state=False)
    complete = surface.layout(ServiceRegistry())

    host_ids = _ids(state_host)
    visual_ids = _ids(visual)
    complete_ids = _ids(complete)

    assert len(host_ids) == len(set(host_ids))
    assert len(host_ids + visual_ids) == len(set(host_ids + visual_ids))
    assert set(host_ids).isdisjoint(visual_ids)
    assert set(host_ids + visual_ids) == set(complete_ids)

    for identifier in (LOCATION_ID, STATUS_STORE_ID, REFRESH_SIGNAL_ID,
                       'tools-source-updated', workflow_draft_id('tools')):
        assert json.dumps(identifier, sort_keys=True) in host_ids
        assert json.dumps(identifier, sort_keys=True) not in visual_ids
    assert json.dumps(workflow_draft_id('hidden'), sort_keys=True) not in host_ids
    assert json.dumps('hidden-source-updated') not in host_ids

    stores = {json.dumps(item.id, sort_keys=True): item
              for item in _components(state_host) if isinstance(item, dcc.Store)}
    assert stores[json.dumps(workflow_draft_id('tools'), sort_keys=True)].storage_type == 'memory'
    assert stores[json.dumps(workflow_saved_draft_id('tools'), sort_keys=True)].storage_type == 'local'


def test_default_manager_layout_preserves_own_state_and_navigation() -> None:
    surface = _surface()
    standard = surface.layout(ServiceRegistry())
    ids = _ids(standard)
    assert json.dumps(LOCATION_ID) in ids
    assert json.dumps(workflow_draft_id('tools'), sort_keys=True) in ids
    assert json.dumps(workflow_draft_id('hidden'), sort_keys=True) not in ids
