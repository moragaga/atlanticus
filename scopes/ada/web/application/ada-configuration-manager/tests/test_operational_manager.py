from __future__ import annotations

from types import SimpleNamespace

from dash import no_update

from ada.web.application.configuration_manager.operational import (
    OperationalManagerContext,
    _position_options,
    build_operational_manager_layout,
    create_operational_manager_entry,
    register_operational_callbacks,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
    assignment_source_key,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore

USER_ID = 'user:' + 'a' * 24


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


def _context(tmp_path, *, allowed=True):
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

    return OperationalManagerContext(
        service=service,
        promoted_users=lambda: (SimpleNamespace(user_id=USER_ID, display_name='Operator'),),
        principal=principal,
    )


def test_catalog_options_distinguish_inactive_entries():
    catalog = OperationalCatalog(positions=(Position('engineering', 'Engineering', active=False),))
    assert _position_options(catalog)[0]['disabled'] is True
    assert _position_options(catalog, include_inactive=True)[0]['disabled'] is False


def test_manager_requires_operational_access(tmp_path):
    context = _context(tmp_path, allowed=False)
    assert context.can_manage() is False
    assert create_operational_manager_entry(context).access_key == 'operational.manage'
    assert build_operational_manager_layout(context) is not None


def test_manager_saves_catalog_and_assignment_with_distinct_sources(tmp_path):
    context = _context(tmp_path)
    assert build_operational_manager_layout(context) is not None
    app = FakeApp()
    register_operational_callbacks(app, context)
    new_catalog_rev, _, _, selected, _ = app.registered['save_position'](
        1,
        None,
        'engineering',
        'Engineer',
        ['active'],
        None,
    )
    assert selected == 'engineering'
    assert new_catalog_rev is not None
    assert context.service.catalog_for_read().position('engineering') is not None

    _, _, _, revision = app.registered['select_user'](USER_ID)
    updated_revision, _ = app.registered['save_assignment'](
        1,
        USER_ID,
        'mina',
        'engineering',
        2,
        revision,
    )
    assert updated_revision is not None
    assert context.service.assignment_for_read(USER_ID).area_id == 'mina'
    assert context.service.assignment_for_read(USER_ID).position_id == 'engineering'
    assert context.service.assignment_for_read(USER_ID).group_id == 2
    assert context.service.project_current(CATALOG_SOURCE_KEY) is not None
    assert context.service.project_current(assignment_source_key(USER_ID)) is not None


def test_manager_detects_stale_assignment_and_catalog(tmp_path):
    context = _context(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, context)
    result = app.registered['save_position'](1, None, 'first', 'First', ['active'], None)
    assert result[0] is not None
    stale = app.registered['save_position'](2, None, 'second', 'Second', ['active'], None)
    assert stale[0] is no_update
    assert context.service.catalog_for_read().position('second') is None


def test_manager_callbacks_enforce_permission(tmp_path):
    context = _context(tmp_path, allowed=False)
    app = FakeApp()
    register_operational_callbacks(app, context)
    result = app.registered['save_assignment'](1, USER_ID, 'mina', None, 1, None)
    assert result[0] is no_update
    assert context.service.assignment_for_read(USER_ID).area_id is None


def test_manager_does_not_assign_unknown_user(tmp_path):
    context = _context(tmp_path)
    app = FakeApp()
    register_operational_callbacks(app, context)
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
