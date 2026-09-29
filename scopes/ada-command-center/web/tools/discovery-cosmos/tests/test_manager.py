from __future__ import annotations

import pytest

from ada_command_center.web.tools.catalog import ToolCatalogStore
from ada_command_center.web.tools.discovery_cosmos.manager import (
    ToolCatalogManagerConflictError,
    ToolCatalogManagerService,
)
from atlanticus.connectivity.cosmos import CosmosSettings

from .test_discovery import CosmosStub, _seed


class SharedCosmos(CosmosStub):
    def __init__(self, data: dict) -> None:
        super().__init__()
        self.items = data
        self.closed = False

    def close(self) -> None:
        self.closed = True


class MemoryCatalog(ToolCatalogStore):
    def __init__(self) -> None:
        self.snapshot = None
        self.writes = 0

    def get_current(self):
        return self.snapshot

    def replace_current(self, snapshot):
        self.snapshot = snapshot
        self.writes += 1
        return snapshot


def _fixture():
    seeded = CosmosStub()
    _seed(seeded, namespace='mine', tool_key='mine')
    database = seeded.items
    clients = []
    settings = CosmosSettings(
        endpoint='https://test.documents.azure.com', database_name='mine', key='sensitive-key'
    )

    def factory(_settings):
        client = SharedCosmos(database)
        clients.append(client)
        return client

    catalog = MemoryCatalog()
    service = ToolCatalogManagerService(
        catalog=catalog,
        connection_provider=lambda: {'mine': settings},
        client_factory=factory,
    )
    return service, catalog, database, clients


def test_inspection_is_read_only_and_does_not_expose_secrets() -> None:
    manager, catalog, _, clients = _fixture()
    preview = manager.inspect()
    assert preview.can_confirm
    assert catalog.writes == 0
    assert clients[0].closed
    assert preview.connections[0].tools[0].tool_key == 'mine'
    assert 'sensitive-key' not in repr(preview)


def test_confirm_reinspects_then_publishes_existing_catalog() -> None:
    manager, catalog, _, clients = _fixture()
    preview = manager.inspect()
    result = manager.confirm(
        expected_fingerprint=preview.fingerprint,
        expected_current_revision=preview.current_revision,
    )
    assert result.revision == catalog.get_current().revision
    assert tuple(item.tool_key for item in result.tools) == ('mine',)
    assert catalog.writes == 1
    assert len(clients) == 2
    assert all(client.closed for client in clients)
    assert manager.adopted().tools[0].tool_key == 'mine'


def test_changed_projection_blocks_publish() -> None:
    manager, catalog, database, clients = _fixture()
    preview = manager.inspect()
    for record in database.values():
        record['source_release_id'] = 'changed-release'
    with pytest.raises(ToolCatalogManagerConflictError, match='inspect again'):
        manager.confirm(
            expected_fingerprint=preview.fingerprint,
            expected_current_revision=preview.current_revision,
        )
    assert catalog.writes == 0
    assert all(client.closed for client in clients)


def test_incomplete_discovery_cannot_publish() -> None:
    manager, catalog, database, _ = _fixture()
    database.clear()
    preview = manager.inspect()
    assert not preview.can_confirm
    with pytest.raises(ToolCatalogManagerConflictError, match='blocking'):
        manager.confirm(
            expected_fingerprint=preview.fingerprint,
            expected_current_revision=preview.current_revision,
        )
    assert catalog.writes == 0


def test_confirm_requires_complete_review_signature() -> None:
    manager, catalog, _, clients = _fixture()
    with pytest.raises(ToolCatalogManagerConflictError, match='invalid'):
        manager.confirm(expected_fingerprint='wrong', expected_current_revision=None)
    assert catalog.writes == 0
    assert not clients
