from __future__ import annotations

from dash import no_update

from ada.web.application.configuration_manager.operational import (
    OperationalManagerContext,
    register_operational_callbacks,
)
from ada.web.operational.identification import OperationalIdentificationService
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


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


def test_manager_creates_ids_server_side_and_reuses_them_during_edits(tmp_path):
    service = OperationalIdentificationService(
        source_store=LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source')),
        projections=MemoryProjection(),
        users=NoUsers(),
    )

    def principal():
        return ManagerPrincipal(
            subject_id='admin',
            display_name='Admin',
            profile_keys=('basic',),
            access_keys=('operational.manage',),
        )

    context = OperationalManagerContext(
        service=service,
        promoted_users=lambda: (),
        principal=principal,
    )
    app = FakeApp()
    register_operational_callbacks(app, context)
    saved = app.registered['save_position'](
        1,
        None,
        'a_user_supplied_id',
        'Operador',
        ['active'],
        None,
    )
    identifier = saved[3]
    assert identifier != 'a_user_supplied_id'
    assert identifier.startswith('position_')
    current, catalog = service.catalog_for_edit()
    assert catalog.position(identifier).label == 'Operador'
    edited = app.registered['save_position'](
        2,
        identifier,
        identifier,
        'Operador de sala',
        ['active'],
        current.current.release_ref.release_id.value,
    )
    assert edited[3] == identifier
    assert service.catalog_for_edit()[1].position(identifier).label == 'Operador de sala'
    latest, _catalog = service.catalog_for_edit()
    changed = app.registered['save_position'](
        3,
        identifier,
        'tampered_id',
        'Inválido',
        ['active'],
        latest.current.release_ref.release_id.value,
    )
    assert changed[0] is no_update
    assert service.catalog_for_edit()[1].position(identifier).label == 'Operador de sala'
