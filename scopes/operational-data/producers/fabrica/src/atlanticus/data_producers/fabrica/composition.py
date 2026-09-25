from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from atlanticus.connectivity.storage import StorageClient, StorageSettings
from atlanticus.data_producers.fabrica.job import FabricaJob
from atlanticus.data_producers.fabrica.materialization import FabricaMaterializer
from atlanticus.data_producers.fabrica.models import FabricaStreamDefinition
from atlanticus.data_producers.fabrica.producer_state import FabricaProducerState
from atlanticus.data_producers.fabrica.source import FabricaStorageSource
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
from atlanticus.runtime import RuntimeConfiguration
from atlanticus.state import AtomicStateStore


@dataclass(frozen=True, slots=True)
class FabricaStorageConnection:
    settings: StorageSettings
    container_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.settings, StorageSettings):
            raise TypeError('settings must be a StorageSettings')
        if not isinstance(self.container_name, str) or not self.container_name.strip():
            raise ValueError('container_name is required')
        object.__setattr__(self, 'container_name', self.container_name.strip())


@dataclass(slots=True)
class FabricaDataProducerComponents:
    dataset_runtime: DatasetRuntime
    storages: Mapping[str, StorageClient]
    materializers: tuple[FabricaMaterializer, ...]
    producer_state: FabricaProducerState
    job: FabricaJob


def build_fabrica_data_producer(
    *,
    runtime_configuration: RuntimeConfiguration,
    definitions: tuple[FabricaStreamDefinition, ...],
    connections: Mapping[str, FabricaStorageConnection],
    idle_seconds: int,
    producer_key: str = 'fabrica',
    dataset_namespace: tuple[str, ...] = ('fabrica',),
) -> FabricaDataProducerComponents:
    if not isinstance(runtime_configuration, RuntimeConfiguration):
        raise TypeError('runtime_configuration must be a RuntimeConfiguration')
    definitions = tuple(definitions)
    if not definitions or not all(isinstance(item, FabricaStreamDefinition) for item in definitions):
        raise TypeError('definitions must contain FabricaStreamDefinition values')
    keys = [definition.stream_key for definition in definitions]
    if len(set(keys)) != len(keys):
        raise ValueError('stream keys must be unique')
    if set(connections) != set(keys):
        raise ValueError('connections must match configured streams')
    if not isinstance(idle_seconds, int) or isinstance(idle_seconds, bool) or idle_seconds <= 0:
        raise ValueError('idle_seconds must be an integer greater than zero')
    enabled = tuple(item for item in definitions if item.metrics)
    storages = {
        item.stream_key: StorageClient(settings=connections[item.stream_key].settings)
        for item in enabled
    }
    dataset_runtime = DatasetRuntime(
        store=ParquetDatasetStore(root=runtime_configuration.application_root / 'datasets')
    )
    materializers = tuple(
        FabricaMaterializer(
            source=FabricaStorageSource(
                client=storages[item.stream_key],
                container_name=connections[item.stream_key].container_name,
                definition=item,
            ),
            runtime=dataset_runtime,
            definition=item,
            dataset_namespace=dataset_namespace,
        )
        for item in enabled
    )
    producer_state = FabricaProducerState(
        store=AtomicStateStore(
            volume_path=runtime_configuration.volume_path,
            application=runtime_configuration.application,
        ),
        producer_key=producer_key,
    )
    return FabricaDataProducerComponents(
        dataset_runtime=dataset_runtime,
        storages=MappingProxyType(storages),
        materializers=materializers,
        producer_state=producer_state,
        job=FabricaJob(materializers=materializers, producer_state=producer_state, idle_seconds=idle_seconds),
    )
