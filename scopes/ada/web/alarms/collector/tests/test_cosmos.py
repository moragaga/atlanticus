import pytest

from ada.web.alarms.collector.cosmos import CosmosAlarmLiveReader
from ada.web.alarms.collector.models import AlarmLiveReadError
from atlanticus.connectivity.cosmos import CosmosError


class FakeClient:
    def __init__(self):
        self.calls = []

    def find_item(self, **kwargs):
        self.calls.append(kwargs)
        return None


def test_reader_uses_point_lookup_with_tool_partition() -> None:
    client = FakeClient()
    reader = CosmosAlarmLiveReader(client=client)
    assert reader.read(tool_key='tool-a') is None
    assert client.calls == [{
        'container_name': 'alarm-live-projection',
        'item_id': 'alarm-live:tool-a',
        'partition_key': 'tool-a',
    }]


def test_reader_converts_cosmos_error() -> None:
    class Broken:
        def find_item(self, **kwargs):
            raise CosmosError('offline')

    with pytest.raises(AlarmLiveReadError):
        CosmosAlarmLiveReader(client=Broken()).read(tool_key='tool-a')


def test_missing_database_is_a_recoverable_read_failure() -> None:
    class MissingDatabase:
        def find_item(self, **kwargs):
            raise CosmosError('Database does not exist')

    with pytest.raises(AlarmLiveReadError, match='Could not read Alarm Live from Cosmos') as exc:
        CosmosAlarmLiveReader(client=MissingDatabase()).read(tool_key='tool-a')
    assert isinstance(exc.value.__cause__, CosmosError)
