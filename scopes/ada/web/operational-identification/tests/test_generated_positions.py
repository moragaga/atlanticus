from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalCatalog,
    OperationalIdentificationService,
    OperationalReferenceError,
    Position,
)
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


class ProjectionMemory(ProjectionStore):
    def __init__(self):
        self.records = {}

    def get_active(self, source_key):
        return self.records.get(source_key)

    def replace_active(self, projection):
        self.records[projection.source_key] = projection
        return projection


class UsersMemory:
    def get(self, user_id):
        return SimpleNamespace(user_id=user_id)


def service_for(tmp_path):
    return OperationalIdentificationService(
        source_store=LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source')),
        projections=ProjectionMemory(),
        users=UsersMemory(),
    )


def test_backend_generates_unique_immutable_ids_and_keeps_the_original_during_edits(tmp_path):
    service = service_for(tmp_path)
    original, _catalog = service.catalog_for_edit()
    first, _release = service.create_position(label='Operador', actor='admin', expected=original)
    assert first.id.startswith('position_')
    assert UUID(hex=first.id.removeprefix('position_')).version == 4
    updated, _catalog = service.catalog_for_edit()
    second, _release = service.create_position(label='Supervisor', actor='admin', expected=updated)
    assert first.id != second.id
    current, catalog = service.catalog_for_edit()
    changed = OperationalCatalog(
        positions=tuple(
            Position(item.id, 'Operador senior', active=False) if item.id == first.id else item
            for item in catalog.positions
        )
    )
    service.publish_catalog(changed, actor='admin', expected=current)
    latest, read_back = service.catalog_for_edit()
    assert latest.current is not None
    assert read_back.position(first.id).label == 'Operador senior'
    assert not read_back.position(first.id).active
    service.project_current(CATALOG_SOURCE_KEY)
    assert service.catalog_for_read() == read_back


def test_stale_snapshot_does_not_create_a_new_position(tmp_path):
    service = service_for(tmp_path)
    stale, _catalog = service.catalog_for_edit()
    service.create_position(label='Primero', actor='admin', expected=stale)
    with pytest.raises(OperationalReferenceError, match='changed'):
        service.create_position(label='Segundo', actor='admin', expected=stale)
    assert tuple(item.label for item in service.catalog_for_edit()[1].positions) == ('Primero',)
