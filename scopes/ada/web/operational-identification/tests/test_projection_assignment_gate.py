from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    OperationalIdentificationService,
    OperationalReferenceError,
    Position,
    assignment_source_key,
)
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore

USER_A = 'user:' + 'a' * 24
USER_B = 'user:' + 'b' * 24


class ProjectionMemory(ProjectionStore):
    def __init__(self) -> None:
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class UsersMemory:
    def get(self, user_id):
        return SimpleNamespace(user_id=user_id) if user_id in {USER_A, USER_B} else None


def service_for(tmp_path):
    return OperationalIdentificationService(
        source_store=LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source')),
        projections=ProjectionMemory(),
        users=UsersMemory(),
    )


def publish_position(service, *, active=True):
    snapshot, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog(positions=(Position('engineer', 'Ingeniero', active=active),)),
        actor='admin',
        expected=snapshot,
    )


def publish_assignment(service, user_id, **values):
    snapshot, _ = service.assignment_for_edit(user_id)
    return service.publish_assignment(
        OperationalAssignment(user_id=user_id, **values),
        actor='admin',
        expected=snapshot,
    )


def test_new_position_requires_active_projection_before_any_source_write(tmp_path):
    service = service_for(tmp_path)
    publish_position(service)
    snapshot, _ = service.assignment_for_edit(USER_A)

    with pytest.raises(OperationalReferenceError, match='must be projected'):
        publish_assignment(service, USER_A, position_id='engineer')

    assert service.assignment_for_edit(USER_A)[0] == snapshot
    service.project_current(CATALOG_SOURCE_KEY)
    publish_assignment(service, USER_A, position_id='engineer')
    assert service.assignment_for_edit(USER_A)[1].position_id == 'engineer'


def test_pending_catalog_publication_blocks_new_positions_not_existing_edits(tmp_path):
    service = service_for(tmp_path)
    publish_position(service)
    service.project_current(CATALOG_SOURCE_KEY)
    publish_assignment(service, USER_A, position_id='engineer')

    snapshot, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero actualizado'),)),
        actor='admin',
        expected=snapshot,
    )

    with pytest.raises(OperationalReferenceError, match='outdated'):
        publish_assignment(service, USER_B, position_id='engineer')

    publish_assignment(service, USER_A, position_id='engineer', group_id=3)
    publish_assignment(service, USER_B, area_id='mina', group_id=1)
    service.project_current(CATALOG_SOURCE_KEY)
    publish_assignment(service, USER_B, area_id='mina', position_id='engineer', group_id=1)


def test_inactive_position_can_only_be_kept_by_current_assignee(tmp_path):
    service = service_for(tmp_path)
    publish_position(service)
    service.project_current(CATALOG_SOURCE_KEY)
    publish_assignment(service, USER_A, position_id='engineer')

    snapshot, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero', active=False),)),
        actor='admin',
        expected=snapshot,
    )
    service.project_current(CATALOG_SOURCE_KEY)

    with pytest.raises(OperationalReferenceError, match='unavailable'):
        publish_assignment(service, USER_B, position_id='engineer')

    publish_assignment(service, USER_A, position_id='engineer', group_id=4)
    assert service.assignment_for_edit(USER_A)[1].group_id == 4


def test_catalog_projection_contains_reference_areas_and_groups(tmp_path):
    service = service_for(tmp_path)
    publish_position(service)
    service.project_current(CATALOG_SOURCE_KEY)
    document = service.catalog_for_read().to_document()

    assert document['areas'] == [
        {'id': 'mina', 'label': 'Mina'},
        {'id': 'planta', 'label': 'Planta'},
    ]
    assert document['groups'] == [
        {'id': 1, 'label': 'Grupo 1'},
        {'id': 2, 'label': 'Grupo 2'},
        {'id': 3, 'label': 'Grupo 3'},
        {'id': 4, 'label': 'Grupo 4'},
    ]


def test_assignment_projection_stays_independent(tmp_path):
    service = service_for(tmp_path)
    publish_assignment(service, USER_A, group_id=4)
    service.project_current(assignment_source_key(USER_A))
    assert service.assignment_for_read(USER_A).group_id == 4
    assert service.assignment_for_read(USER_B).group_id is None
