from __future__ import annotations

from types import SimpleNamespace

from ada.web.application.configuration_manager import operational_ids as ids
from ada.web.application.configuration_manager.operational import (
    OperationalManagerContext,
    build_operational_manager_layout,
    register_operational_callbacks,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore

USER_ID = 'user:' + 'a' * 24


class ProjectionMemory(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, key):
        return self.records.get(key)

    def replace_active(self, item):
        self.records[item.source_key] = item
        return item


class FakeUsers:
    def get(self, user_id):
        return SimpleNamespace(user_id=user_id) if user_id == USER_ID else None


class FakeApp:
    def __init__(self):
        self.callbacks = {}

    def callback(self, *args, **kwargs):
        def register(callback):
            self.callbacks[callback.__name__] = callback
            return callback
        return register


def context_for(tmp_path):
    return OperationalManagerContext(
        service=OperationalIdentificationService(
            source_store=LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source')),
            projections=ProjectionMemory(),
            users=FakeUsers(),
        ),
        promoted_users=lambda: (SimpleNamespace(user_id=USER_ID, display_name='Operador'),),
        principal=lambda: ManagerPrincipal(
            subject_id='admin',
            display_name='Administrador',
            profile_keys=('basic',),
            access_keys=('operational.manage',),
        ),
    )


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
    context = context_for(tmp_path)
    snapshot, _ = context.service.catalog_for_edit()
    context.service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero'),)),
        actor='admin',
        expected=snapshot,
    )
    layout = build_operational_manager_layout(context)
    components = tuple(descendants(layout))
    assert next(item for item in components if getattr(item, 'id', None) == ids.POSITION).options == []
    assert {'Áreas operacionales', 'Mina · Planta', 'Grupos', '1 · 2 · 3 · 4'}.issubset(
        {item for item in components if isinstance(item, str)}
    )
    app = FakeApp()
    register_operational_callbacks(app, context)

    assert app.callbacks['assignment_position_options'](USER_ID) == []
    context.service.project_current(CATALOG_SOURCE_KEY)
    assert app.callbacks['assignment_position_options'](USER_ID) == [
        {'label': 'Ingeniero', 'value': 'engineer', 'disabled': False},
    ]

    next_snapshot, _ = context.service.catalog_for_edit()
    context.service.publish_catalog(
        OperationalCatalog((
            Position('engineer', 'Ingeniero'),
            Position('supervisor', 'Supervisor'),
        )),
        actor='admin',
        expected=next_snapshot,
    )
    assert app.callbacks['assignment_position_options'](USER_ID) == [
        {'label': 'Ingeniero', 'value': 'engineer', 'disabled': True},
    ]
    context.service.project_current(CATALOG_SOURCE_KEY)
    assert all(
        not item['disabled'] for item in app.callbacks['assignment_position_options'](USER_ID)
    )
