from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.projection.cosmos import (
    TOOL_PROJECTION_STORAGE_RESOURCE,
    CosmosToolProjectionStore,
    CosmosToolProjectionStoreSettings,
)
from ada_command_center.web.tools.catalog import (
    ToolCatalogConsolidator,
    ToolCatalogEntry,
    ToolCatalogStore,
    create_tool_catalog_snapshot,
)
from ada_command_center.web.tools.discovery_cosmos import (
    ToolCatalogConnectionStatus,
    ToolCatalogDiscovery,
    ToolCatalogDiscoveryError,
    ToolCatalogDiscoveryIssue,
)
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerNotFoundError,
    CosmosError,
    CosmosResultLimitError,
)
from atlanticus.web.source.models import SourceKey

from .helpers import tool_projection


class CosmosStub(CosmosClient):
    def __init__(self) -> None:
        self.container_exists = True
        self.read_error = False
        self.extra_rows: list[dict[str, object]] = []
        self.items: dict[tuple[str, str, str], dict[str, object]] = {}
        self.queries = 0
        self.point_reads = 0
        self.writes = 0

    def query_items(
        self,
        *,
        container_name,
        query,
        parameters,
        cross_partition,
        max_items,
        page_size,
    ):
        self.queries += 1
        assert container_name == TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name
        assert cross_partition is True
        assert 0 < max_items <= 256
        assert 0 < page_size <= 100
        assert 'c.partition_key' in query
        if not self.container_exists:
            raise CosmosContainerNotFoundError('not found')
        if self.read_error:
            raise CosmosError('SECRET_VALUE_SHOULD_NEVER_ESCAPE')
        parameters_by_name = {param.name: param.value for param in parameters}
        rows = [
            {'id': document['id'], 'partition_key': document['partition_key']}
            for document in self.items.values()
            if document.get('document_type') == parameters_by_name['@document_type']
            and document.get('source_key') == parameters_by_name['@source_key']
        ] + self.extra_rows
        if len(rows) > max_items:
            raise CosmosResultLimitError(max_items=max_items)
        return tuple(rows)

    def find_item(self, *, container_name, item_id, partition_key):
        self.point_reads += 1
        item = self.items.get((container_name, item_id, partition_key))
        return dict(item) if item is not None else None

    def upsert_item(self, *, container_name, item):
        self.writes += 1
        saved = dict(item)
        self.items[(container_name, saved['id'], saved['partition_key'])] = saved
        return saved


def _seed(
    client: CosmosStub,
    *,
    namespace: str,
    tool_key: str,
    release_id: str = 'release-1',
) -> None:
    store = CosmosToolProjectionStore(
        client=client,
        settings=CosmosToolProjectionStoreSettings.from_namespace(
            container_name=TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name,
            namespace=AdaStorageNamespace('ada', namespace),
        ),
    )
    store.replace_active(tool_projection(tool_key=tool_key, release_id=release_id))


def _discover(
    upstream: Mapping[str, CosmosStub],
    *,
    own: CosmosStub | None = None,
    limit: int = 256,
):
    manager = own or CosmosStub()
    return ToolCatalogDiscovery(
        connections=upstream,
        max_documents_per_connection=limit,
    ).inspect(), manager


def test_reads_multiple_tools_in_same_cosmos_and_excludes_own_connection() -> None:
    shared = CosmosStub()
    own = CosmosStub()
    _seed(shared, namespace='mine', tool_key='mine')
    _seed(shared, namespace='plant', tool_key='plant')
    _seed(own, namespace='internal', tool_key='internal')
    initial_writes = shared.writes

    report, own = _discover({'operations': shared}, own=own)

    assert own.queries == 0
    assert shared.queries == 1
    assert shared.point_reads == 2
    assert shared.writes == initial_writes
    assert len(report.connections) == 1
    assert report.connections[0].status is ToolCatalogConnectionStatus.READY
    assert [tool.tool_key for tool in report.connections[0].tools] == ['mine', 'plant']
    assert report.connections[0].tools[0].configuration.tool_key == 'mine'
    inputs = report.consolidation_inputs(current=None)
    assert len(inputs) == 2
    active_keys = [
        entry.projection.get_active(SourceKey('tools')).payload.tool_key for entry in inputs
    ]
    assert active_keys == ['mine', 'plant']


class CatalogStoreStub(ToolCatalogStore):
    def __init__(self) -> None:
        self.current = None

    def get_current(self):
        return self.current

    def replace_current(self, snapshot):
        self.current = snapshot
        return snapshot


def test_discovered_sources_feed_existing_consolidator() -> None:
    mine, plant = CosmosStub(), CosmosStub()
    _seed(mine, namespace='mine', tool_key='mine')
    _seed(plant, namespace='plant', tool_key='plant')
    report, _ = _discover({'mine': mine, 'plant': plant})
    catalog_store = CatalogStoreStub()
    assert catalog_store.get_current() is None

    confirmed = ToolCatalogConsolidator(
        inputs=report.consolidation_inputs(current=catalog_store.get_current()),
        store=catalog_store,
        clock=lambda: datetime(2026, 9, 21, 12, tzinfo=UTC),
    ).refresh()

    assert catalog_store.get_current() == confirmed
    assert tuple(item.tool_key for item in confirmed.tools) == ('mine', 'plant')


def test_consolidation_input_fails_if_source_changes_after_inspection() -> None:
    upstream = CosmosStub()
    _seed(upstream, namespace='mine', tool_key='mine')
    report, _ = _discover({'operations': upstream})
    inputs = report.consolidation_inputs(current=None)
    _seed(upstream, namespace='mine', tool_key='mine', release_id='release-2')

    with pytest.raises(ToolCatalogDiscoveryError, match='changed after discovery'):
        inputs[0].projection.get_active(SourceKey('tools'))


def test_distinguishes_missing_container_from_container_without_tools() -> None:
    missing = CosmosStub()
    missing.container_exists = False
    empty = CosmosStub()
    valid = CosmosStub()
    _seed(valid, namespace='mine', tool_key='mine')

    report, _ = _discover({'missing': missing, 'empty': empty, 'valid': valid})

    assert {item.connection_name: item.status for item in report.connections} == {
        'empty': ToolCatalogConnectionStatus.NO_TOOLS,
        'missing': ToolCatalogConnectionStatus.NO_CONTAINER,
        'valid': ToolCatalogConnectionStatus.READY,
    }
    assert len(report.consolidation_inputs(current=None)) == 1


def test_connection_error_blocks_all_inputs_without_disclosing_secrets() -> None:
    failed = CosmosStub()
    failed.read_error = True
    valid = CosmosStub()
    _seed(valid, namespace='mine', tool_key='mine')

    report, _ = _discover({'failed': failed, 'valid': valid})

    failure = next(item for item in report.connections if item.connection_name == 'failed')
    assert failure.issue is ToolCatalogDiscoveryIssue.QUERY_FAILED
    assert 'SECRET_VALUE' not in repr(report)
    with pytest.raises(ToolCatalogDiscoveryError, match='blocking'):
        report.consolidation_inputs(current=None)


def test_invalid_namespace_blocks_consolidation() -> None:
    invalid = CosmosStub()
    invalid.extra_rows = [{'id': 'fake', 'partition_key': 'not-an-ada-namespace'}]

    report, _ = _discover({'invalid': invalid})

    assert report.connections[0].issue is ToolCatalogDiscoveryIssue.INVALID_NAMESPACE
    with pytest.raises(ToolCatalogDiscoveryError):
        report.consolidation_inputs(current=None)


def test_noncanonical_projection_blocks_consolidation() -> None:
    invalid = CosmosStub()
    invalid.extra_rows = [{'id': 'wrong-id', 'partition_key': 'ada/mine'}]

    report, _ = _discover({'invalid': invalid})

    assert report.connections[0].issue is ToolCatalogDiscoveryIssue.MISSING_PROJECTION
    with pytest.raises(ToolCatalogDiscoveryError):
        report.consolidation_inputs(current=None)


def test_missing_structure_blocks_consolidation() -> None:
    incomplete = CosmosStub()
    _seed(incomplete, namespace='mine', tool_key='mine')
    for document in incomplete.items.values():
        document['payload']['structure'] = None

    report, _ = _discover({'incomplete': incomplete})

    assert report.connections[0].issue is ToolCatalogDiscoveryIssue.MISSING_STRUCTURE
    with pytest.raises(ToolCatalogDiscoveryError):
        report.consolidation_inputs(current=None)


def test_duplicate_namespace_blocks_consolidation() -> None:
    duplicate = CosmosStub()
    _seed(duplicate, namespace='mine', tool_key='mine')
    duplicate.extra_rows = [{'id': 'second-id', 'partition_key': 'ada/mine'}]

    report, _ = _discover({'duplicate': duplicate})

    assert report.connections[0].issue is ToolCatalogDiscoveryIssue.DUPLICATE_NAMESPACE
    with pytest.raises(ToolCatalogDiscoveryError):
        report.consolidation_inputs(current=None)


def test_duplicate_tool_keys_across_connections_block_consolidation() -> None:
    first, second = CosmosStub(), CosmosStub()
    _seed(first, namespace='mine', tool_key='shared')
    _seed(second, namespace='plant', tool_key='shared')

    report, _ = _discover({'first': first, 'second': second})

    assert all(item.status is ToolCatalogConnectionStatus.READY for item in report.connections)
    with pytest.raises(ToolCatalogDiscoveryError, match='duplicate tool_key'):
        report.consolidation_inputs(current=None)


def test_missing_previously_confirmed_tool_requires_explicit_reconciliation() -> None:
    current_projection = tool_projection(tool_key='previous')
    config = current_projection.payload
    assert config.structure is not None
    current = create_tool_catalog_snapshot(
        (
            ToolCatalogEntry(
                tool_key='previous',
                display_name=config.display_name,
                kind=config.kind,
                source_release_id=current_projection.source_release_id,
                structure=config.structure,
            ),
        ),
        generated_at_utc=datetime(2026, 9, 21, 12, tzinfo=UTC),
    )
    replacement = CosmosStub()
    _seed(replacement, namespace='replacement', tool_key='replacement')
    report, _ = _discover({'replacement': replacement})

    with pytest.raises(ToolCatalogDiscoveryError, match='cannot silently remove'):
        report.consolidation_inputs(current=current)


def test_query_limit_blocks_instead_of_returning_partial_results() -> None:
    many = CosmosStub()
    _seed(many, namespace='mine', tool_key='mine')
    _seed(many, namespace='plant', tool_key='plant')

    report, _ = _discover({'many': many}, limit=1)

    assert report.connections[0].issue is ToolCatalogDiscoveryIssue.LIMIT_EXCEEDED
    with pytest.raises(ToolCatalogDiscoveryError):
        report.consolidation_inputs(current=None)


def test_no_tools_anywhere_cannot_construct_consolidator_inputs() -> None:
    report, _ = _discover({'empty': CosmosStub()})

    with pytest.raises(ToolCatalogDiscoveryError, match='no confirmed candidates'):
        report.consolidation_inputs(current=None)


def test_requires_external_sources_and_rejects_reserved_command_center_alias() -> None:
    own = CosmosStub()
    with pytest.raises(ValueError, match='External Cosmos connections'):
        ToolCatalogDiscovery(connections={})
    with pytest.raises(TypeError, match='Named Cosmos connections'):
        ToolCatalogDiscovery(connections={'command-center': own})
    with pytest.raises(ValueError, match='document limit'):
        ToolCatalogDiscovery(
            connections={'external': CosmosStub()}, max_documents_per_connection=257
        )
