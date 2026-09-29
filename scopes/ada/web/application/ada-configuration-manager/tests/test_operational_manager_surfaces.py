from __future__ import annotations

from types import SimpleNamespace

import dash_bootstrap_components as dbc

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


def test_assignment_is_initial_and_catalog_remains_independent(tmp_path):
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
    assert _find(layout, ids.VIEW).data == 'assignments'
    assert _find(layout, ids.POSITION_TAB).children == 'Datos operacionales'
    assert _find(layout, ids.ASSIGN_TAB).children == 'Asignación'
    assert getattr(_find(layout, ids.POSITION_TAB), 'aria-controls') == ids.POSITION_PANEL
    assert getattr(_find(layout, ids.ASSIGN_TAB), 'aria-controls') == ids.ASSIGN_PANEL
    assert _find(layout, ids.CATALOG_REPROJECT) is not None
    assert _find(layout, ids.ASSIGN_FEEDBACK) is not None
    assert _find(layout, ids.ASSIGNMENT_REPROJECT) is not None
    assert _find(layout, ids.CATALOG_METADATA) is not None
    assert _find(layout, ids.ASSIGN_LIST) is not None
    assert _find(layout, ids.ASSIGN_SIZE) is not None
    assert _find(layout, ids.POSITION_SIZE) is not None
    assert isinstance(_find(layout, ids.POSITION_ACTIVE), dbc.Checklist)
    cargo_modal = _find(layout, ids.POSITION_MODAL)
    assert getattr(cargo_modal.children[1], 'aria-label') == 'Cargo'
    tabs = _find(layout, ids.ASSIGN_TAB).children, _find(layout, ids.POSITION_TAB).children
    assert tabs == ('Asignación', 'Datos operacionales')
    assert getattr(_find(layout, ids.ASSIGN_TAB), 'aria-selected') == 'true'
    assert getattr(_find(layout, ids.POSITION_TAB), 'aria-selected') == 'false'


def test_primary_navigation_selects_catalog_and_assignments(monkeypatch):
    from dash import no_update

    from ada.web.application.configuration_manager import (
        operational_callbacks,
        operational_ids as ids,
    )

    class FakeApp:
        def __init__(self):
            self.callbacks = {}

        def callback(self, *_args, **_kwargs):
            def register(fn):
                self.callbacks[fn.__name__] = fn
                return fn

            return register

    app = FakeApp()
    operational_callbacks.register_operational_callbacks(app, object())
    event = SimpleNamespace(triggered_id=ids.ASSIGN_TAB)
    monkeypatch.setattr(operational_callbacks, 'ctx', event)
    assert app.callbacks['change_tab'](0, 1) == 'assignments'
    assignment = app.callbacks['display_tab']('assignments')
    assert assignment[-2:] == ('false', 'true')
    assert assignment[2] == 'ada-operational-admin__surface'
    assert 'ada-operational-admin__surface--active' in assignment[3]

    event.triggered_id = ids.POSITION_TAB
    assert app.callbacks['change_tab'](1, 0) == 'positions'
    catalog = app.callbacks['display_tab']('positions')
    assert catalog[-2:] == ('true', 'false')
    assert app.callbacks['change_tab'](0, 0) is no_update
