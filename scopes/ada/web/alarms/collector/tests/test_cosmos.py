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



def test_missing_alarm_container_has_distinct_exception() -> None:
    from ada.web.alarms.collector.models import AlarmLiveContainerMissingError
    from atlanticus.connectivity.cosmos import CosmosContainerNotFoundError

    class Broken:
        def find_item(self, **kwargs):
            raise CosmosContainerNotFoundError('container missing')

    with pytest.raises(AlarmLiveContainerMissingError):
        CosmosAlarmLiveReader(client=Broken()).read(tool_key='tool-a')


def test_missing_alarm_document_is_not_container_failure() -> None:
    reader = CosmosAlarmLiveReader(client=FakeClient())
    assert reader.read(tool_key='tool-a') is None


def test_ambiguous_alarm_404_checks_container_only_once(monkeypatch) -> None:
    from ada.web.alarms.collector import cosmos as module
    from ada.web.alarms.collector.models import AlarmLiveContainerMissingError
    from atlanticus.connectivity.cosmos import CosmosContainerNotFoundError

    called = []

    class Inventory:
        def __init__(self, *, client):
            pass

        def read_container(self, *, container_name):
            called.append(container_name)
            raise CosmosContainerNotFoundError('container not found')

    monkeypatch.setattr(module, 'CosmosClient', FakeClient)
    monkeypatch.setattr(module, 'CosmosInventory', Inventory)
    reader = CosmosAlarmLiveReader(client=FakeClient())
    with pytest.raises(AlarmLiveContainerMissingError):
        reader.read(tool_key='tool-a')
    with pytest.raises(AlarmLiveContainerMissingError):
        reader.read(tool_key='tool-a')
    assert called == ['alarm-live-projection']
