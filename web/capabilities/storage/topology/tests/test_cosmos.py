import pytest

from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    StorageTopologyConfigurationError,
)


def test_cosmos_container_topology_is_immutable_and_durable_by_default() -> None:
    topology = CosmosContainerTopology(partition_key_path='/id')

    assert topology.partition_key_path == '/id'
    assert topology.default_ttl_seconds is None
    with pytest.raises(AttributeError):
        topology.partition_key_path = '/issuer'


@pytest.mark.parametrize('value', ['', '/', ' id', '/id ', '/a//b', 'id', '/id\x00'])
def test_cosmos_container_topology_rejects_invalid_partition_key_path(value: str) -> None:
    with pytest.raises(StorageTopologyConfigurationError):
        CosmosContainerTopology(partition_key_path=value)


@pytest.mark.parametrize('value', [0, -2, True])
def test_cosmos_container_topology_rejects_invalid_ttl(value: int) -> None:
    with pytest.raises(StorageTopologyConfigurationError):
        CosmosContainerTopology(partition_key_path='/id', default_ttl_seconds=value)


@pytest.mark.parametrize('value', [None, -1, 1, 3600])
def test_cosmos_container_topology_accepts_supported_ttl_values(value: int | None) -> None:
    topology = CosmosContainerTopology(partition_key_path='/id', default_ttl_seconds=value)

    assert topology.default_ttl_seconds == value
