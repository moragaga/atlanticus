import pytest

from ada.kpis.materialization import (
    KPI_REGISTRY_CONTAINER_NAME,
    KPI_REGISTRY_ITEM_ID,
    KPI_REGISTRY_PARTITION_VALUE,
)
from ada.processes.kpi_materialization.errors import (
    KpiMaterializationAcquisitionError,
)
from ada.processes.kpi_materialization.repository import (
    CosmosKpiRegistryRepository,
)
from tests.support import projection


class Client:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def find_item(self, **kwargs):
        self.calls.append(kwargs)
        return self.value


def test_repository_reads_fixed_registry_identity():
    client = Client(projection())
    repository = CosmosKpiRegistryRepository(tool_key='tool_a', client=client)

    assert repository.read() == projection()
    assert client.calls == [
        {
            'container_name': KPI_REGISTRY_CONTAINER_NAME,
            'item_id': KPI_REGISTRY_ITEM_ID,
            'partition_key': KPI_REGISTRY_PARTITION_VALUE,
        }
    ]


def test_repository_missing_registry_is_tool_scoped_error():
    repository = CosmosKpiRegistryRepository(tool_key='tool_a', client=Client(None))

    with pytest.raises(KpiMaterializationAcquisitionError, match='tool_a'):
        repository.read()
