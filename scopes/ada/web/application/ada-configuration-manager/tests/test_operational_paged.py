from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.configuration_manager.operational import OperationalAssignmentContext
from ada.web.application.configuration_manager.operational_layout import (
    _page_tokens,
    page_label,
    render_assignment_list,
    render_position_list,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    OperationalIdentificationService,
    Position,
    assignment_source_key,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.pagination import PageRequest
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


class MemoryProjectionStore(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class PromotedUsers:
    def __init__(self, count):
        self.users = tuple(
            SimpleNamespace(
                user_id=f'user:{number:024x}',
                display_name=f'Usuario {number:02}',
                email=f'user{number}@example.test',
                enabled=True,
            )
            for number in range(count)
        )
        self.reads = []

    def list_users(self):
        return self.users

    def get(self, user_id):
        self.reads.append(user_id)
        return next((user for user in self.users if user.user_id == user_id), None)


def make_context(tmp_path, count=23):
    users = PromotedUsers(count)
    service = OperationalIdentificationService(
        source_store=LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source')),
        projections=MemoryProjectionStore(),
        users=users,
    )

    def principal():
        return ManagerPrincipal(
            subject_id='operator',
            display_name='Operator',
            profile_keys=('basic',),
            access_keys=('operational.manage',),
        )

    return OperationalAssignmentContext(
        service=service,
        promoted_users=users.list_users,
        principal=principal,
    ), users


def _strings(component):
    if isinstance(component, str):
        return component
    if isinstance(component, (tuple, list)):
        return ' '.join(_strings(child) for child in component)
    return _strings(getattr(component, 'children', None)) if component is not None else ''


def test_assignments_paginate_promoted_users_without_reading_off_page(tmp_path):
    context, users = make_context(tmp_path)
    first, first_page = render_assignment_list(context, None, 1, 10)
    assert first_page.total_count == 23
    assert len(first_page.items) == 10
    assert page_label(first_page) == '1–10 de 23'
    assert len(users.reads) == 10
    assert 'Usuario 00' in _strings(first)
    assert 'Usuario 10' not in _strings(first)
    users.reads.clear()
    last, last_page = render_assignment_list(context, None, 99, 10)
    assert last_page.request.page_number == 3
    assert len(last_page.items) == 3
    assert page_label(last_page) == '21–23 de 23'
    assert len(users.reads) == 3
    assert 'Usuario 22' in _strings(last)
    users.reads.clear()
    second, second_page = render_assignment_list(context, 'usuario 0', 1, 20)
    assert second_page.total_count == 10
    assert second_page.request.page_size == 20
    assert len(users.reads) == 10
    assert 'Usuario 09' in _strings(second)


def test_position_catalog_has_same_10_20_pagination_and_search():
    catalog = OperationalCatalog(
        tuple(Position(f'cargo-{number:02}', f'Cargo {number:02}') for number in range(23))
    )
    first, first_page = render_position_list(catalog, None, 1, 10)
    assert first_page.total_count == 23
    assert page_label(first_page) == '1–10 de 23'
    assert 'Cargo 00' in _strings(first)
    assert 'Cargo 10' not in _strings(first)
    last, last_page = render_position_list(catalog, None, 99, 10)
    assert page_label(last_page) == '21–23 de 23'
    assert 'Cargo 22' in _strings(last)
    larger, larger_page = render_position_list(catalog, None, 2, 20)
    assert larger_page.request.page_size == 20
    assert page_label(larger_page) == '21–23 de 23'
    assert 'Cargo 22' in _strings(larger)
    searched, search_page = render_position_list(catalog, 'cargo 02', 1, 20)
    assert search_page.total_count == 1
    assert 'Cargo 02' in _strings(searched)
    assert _page_tokens(5, 12) == (1, None, 3, 4, 5, 6, 7, None, 12)
    with pytest.raises(ValueError):
        PageRequest(1, 15)


def test_source_publication_and_projection_are_distinguishable_in_user_list(tmp_path):
    context, users = make_context(tmp_path, 1)
    user_id = users.users[0].user_id
    initial, _page = render_assignment_list(context, None, 1, 10)
    assert 'Sin asignación' in _strings(initial)
    assert 'Sin publicar' in _strings(initial)
    snapshot, _assignment = context.service.assignment_for_edit(user_id)
    context.service.publish_assignment(
        OperationalAssignment(user_id=user_id, area_id='mina', group_id=2),
        actor='operator',
        expected=snapshot,
    )
    published, _page = render_assignment_list(context, None, 1, 10)
    assert 'Con atributos' in _strings(published)
    assert 'Pendiente de proyección' in _strings(published)
    context.service.project_current(assignment_source_key(user_id))
    projected, _page = render_assignment_list(context, None, 1, 10)
    assert 'Sincronizado' in _strings(projected)
    assert 'Grupo: 2' in _strings(projected)
    catalog, _ = context.service.catalog_for_edit()
    assert catalog.current is None
    assert context.service.project_current(CATALOG_SOURCE_KEY) is None


def test_error_does_not_appear_as_missing_assignment(tmp_path):
    context, _users = make_context(tmp_path, 1)

    def unavailable(_user_id):
        raise RuntimeError('unavailable')

    context.service.assignment_for_edit = unavailable
    list_content, page = render_assignment_list(context, None, 1, 10)
    assert page.total_count == 1
    assert 'Datos no disponibles' in _strings(list_content)
    assert 'Sin asignación' not in _strings(list_content)


def test_pagination_navigation_ignores_dynamic_mount_and_uses_clicked_page(monkeypatch):
    from dash import no_update

    from ada.web.application.configuration_manager import operational_callbacks

    selected = SimpleNamespace(triggered_id={'type': 'jump', 'index': 2})
    monkeypatch.setattr(operational_callbacks, 'ctx', selected)

    def next_page(*, current=1, prev=None, next_=None, clicks=None, ids=None):
        return operational_callbacks._next_page(
            current=current,
            previous_clicks=prev,
            next_clicks=next_,
            jump_clicks=clicks,
            jump_ids=ids,
            previous_id='previous',
            next_id='next',
            jump_type='jump',
            reset_ids=('size', 'search'),
        )

    buttons = ({'type': 'jump', 'index': 1}, {'type': 'jump', 'index': 2})
    assert next_page(clicks=[0, 0], ids=buttons) is no_update
    assert next_page(clicks=[0, 1], ids=buttons) == 2
    selected.triggered_id = 'previous'
    assert next_page(current=3, prev=0) is no_update
    assert next_page(current=3, prev=1) == 2
    selected.triggered_id = 'search'
    assert next_page(current=3) == 1
