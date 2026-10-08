from datetime import UTC, datetime

import pytest

from ada.contracts.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY,
    ALARM_CONFIGURATION_CONTAINER_NAME,
    AlarmConfiguration,
    AlarmConfigurationProjection,
    AlarmConfigurationSnapshot,
    alarm_configuration_projection_item_id,
)
from ada.contracts.tools import ToolDependencyManifest
from ada.processes.alarm_materialization import (
    AlarmMaterializationAcquisitionError,
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationContractError,
    CosmosAlarmConfigurationRepository,
)
from atlanticus.connectivity.cosmos import CosmosContainerNotFoundError


class FakeCosmosClient:
    def __init__(self, *, documents=(), error: Exception | None = None) -> None:
        self.documents = tuple(documents)
        self.error = error
        self.calls: list[dict[str, object]] = []

    def query_items(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.documents


def _projection(source_key: str = ALARM_CONFIGURATION_SOURCE_KEY) -> AlarmConfigurationProjection:
    return AlarmConfigurationProjection(
        source_key=source_key,
        source_release_id='alarm-r7',
        source_published_at_utc=datetime(2026, 10, 7, 12, tzinfo=UTC),
        projected_at_utc=datetime(2026, 10, 7, 12, 1, tzinfo=UTC),
        snapshot=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r9',
                tools=(),
            ),
        ),
    )


def _document(projection: AlarmConfigurationProjection | None = None) -> dict[str, object]:
    projection = _projection() if projection is None else projection
    return projection.to_document(
        item_id=alarm_configuration_projection_item_id(ALARM_CONFIGURATION_SOURCE_KEY),
        partition_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )


def _repository(client: FakeCosmosClient) -> CosmosAlarmConfigurationRepository:
    return CosmosAlarmConfigurationRepository(client=client)


def test_repository_reads_only_the_shared_active_projection_address() -> None:
    client = FakeCosmosClient(documents=(_document(),))

    candidate = _repository(client).read_active()

    assert candidate.projection == _projection()
    assert client.calls == [
        {
            'container_name': ALARM_CONFIGURATION_CONTAINER_NAME,
            'query': 'SELECT * FROM c WHERE c.id = @item_id',
            'parameters': (
                {
                    'name': '@item_id',
                    'value': alarm_configuration_projection_item_id(ALARM_CONFIGURATION_SOURCE_KEY),
                },
            ),
            'partition_key': ALARM_CONFIGURATION_SOURCE_KEY,
            'max_items': 1,
        }
    ]


def test_repository_treats_missing_document_as_pending() -> None:
    with pytest.raises(AlarmMaterializationConfigurationPending):
        _repository(FakeCosmosClient()).read_active()


def test_repository_treats_missing_container_as_operational_failure() -> None:
    client = FakeCosmosClient(
        error=CosmosContainerNotFoundError('Cosmos container was not found'),
    )

    with pytest.raises(AlarmMaterializationAcquisitionError) as captured:
        _repository(client).read_active()

    assert not isinstance(captured.value, AlarmMaterializationConfigurationPending)


@pytest.mark.parametrize(
    'mutate',
    [
        lambda value: value.update(id='wrong'),
        lambda value: value.update(partition_key='wrong'),
        lambda value: value.update(schema_version=999),
    ],
)
def test_repository_rejects_invalid_persisted_contract(mutate) -> None:
    document = _document()
    mutate(document)

    with pytest.raises(AlarmMaterializationContractError):
        _repository(FakeCosmosClient(documents=(document,))).read_active()


def test_repository_rejects_projection_from_another_source() -> None:
    with pytest.raises(AlarmMaterializationContractError):
        _repository(
            FakeCosmosClient(documents=(_document(_projection('other-source')),))
        ).read_active()


def test_repository_uses_shared_container_contract() -> None:
    assert ALARM_CONFIGURATION_CONTAINER_NAME == 'alarm-configuration'
