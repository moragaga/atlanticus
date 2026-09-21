from datetime import UTC, datetime

import pytest

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.projection.cosmos import (
    CosmosToolProjectionStore,
    CosmosToolProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


class _CosmosClient:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, object], dict[str, object]] = {}
        self.fail_reads = False
        self.fail_writes = False

    def find_item(
        self,
        *,
        container_name,
        item_id,
        partition_key,
    ):
        if self.fail_reads:
            raise CosmosError('read failed')
        document = self.items.get((container_name, item_id, partition_key))
        return dict(document) if document is not None else None

    def upsert_item(self, *, container_name, item):
        if self.fail_writes:
            raise CosmosError('write failed')
        saved = dict(item)
        self.items[
            (
                container_name,
                str(saved['id']),
                saved['partition_key'],
            )
        ] = saved
        return saved


def _configuration(tool_key: str) -> ToolConfiguration:
    return ToolConfiguration.from_document(
        {
            'tool_key': tool_key,
            'display_name': tool_key.replace('_', ' ').title(),
            'kind': 'process',
            'source_consumption': {
                'tool_key': tool_key,
                'source_keys': ['pi'],
            },
            'source_operational_participation': {
                'tool_key': tool_key,
                'control_sources': [
                    {
                        'source_key': 'pi',
                        'pre_degrading_after_seconds': 200,
                        'degrading_after_seconds': 300,
                    }
                ],
                'additional_observation_source_keys': [],
            },
            'structure': {
                'tool_key': tool_key,
                'kind': 'process',
                'operational_scope': 'mine',
                'components': [
                    {
                        'key': 'center',
                        'display_name': 'Centro',
                        'layout_role': 'center',
                        'subcomponents': [
                            {
                                'key': 'primary',
                                'display_name': 'Principal',
                                'linked_component_keys': [],
                            }
                        ],
                    }
                ],
            },
        }
    )


def _record(tool_key: str) -> ProjectionRecord[ToolConfiguration]:
    published = datetime(2026, 9, 20, 20, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId(f'{tool_key}-release'),
        source_published_at_utc=published,
        projected_at_utc=published,
        payload=_configuration(tool_key),
    )


def _settings(
    tool_namespace: str,
) -> CosmosToolProjectionStoreSettings:
    return CosmosToolProjectionStoreSettings.from_namespace(
        container_name='ada-tool-projection',
        namespace=AdaStorageNamespace(
            application_namespace='conciencia_situacional',
            tool_namespace=tool_namespace,
        ),
    )


def test_cosmos_settings_use_full_application_tool_namespace() -> None:
    settings = _settings('operaciones_integradas')

    assert settings.namespace_key == 'conciencia_situacional/operaciones_integradas'


def test_cosmos_tool_projection_round_trips_exact_record() -> None:
    client = _CosmosClient()
    store = CosmosToolProjectionStore(
        client=client,
        settings=_settings('operaciones_integradas'),
    )
    record = _record('operaciones_integradas')

    assert store.get_active(SourceKey('tools')) is None
    assert store.replace_active(record) == record
    assert store.get_active(SourceKey('tools')) == record


def test_cosmos_tool_namespaces_isolate_same_source_key() -> None:
    client = _CosmosClient()
    operations = CosmosToolProjectionStore(
        client=client,
        settings=_settings('operaciones_integradas'),
    )
    mine = CosmosToolProjectionStore(
        client=client,
        settings=_settings('mina'),
    )

    operations_record = _record('operaciones_integradas')
    mine_record = _record('mina')
    operations.replace_active(operations_record)
    mine.replace_active(mine_record)

    assert operations.get_active(SourceKey('tools')) == operations_record
    assert mine.get_active(SourceKey('tools')) == mine_record
    assert len(client.items) == 2
    assert {key[2] for key in client.items} == {
        'conciencia_situacional/operaciones_integradas',
        'conciencia_situacional/mina',
    }


def test_cosmos_tool_projection_wraps_connector_failures() -> None:
    client = _CosmosClient()
    store = CosmosToolProjectionStore(
        client=client,
        settings=_settings('mina'),
    )

    client.fail_reads = True
    with pytest.raises(Exception, match='Could not read Cosmos Tool projection'):
        store.get_active(SourceKey('tools'))

    client.fail_reads = False
    client.fail_writes = True
    with pytest.raises(Exception, match='Could not write Cosmos Tool projection'):
        store.replace_active(_record('mina'))
