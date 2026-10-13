from types import SimpleNamespace

from ada.web.application.generic.activity import open_durable_activity_repository
from atlanticus.web.users.activity import CosmosUserActivityRepository


def test_activity_repository_uses_dedicated_container_and_closes_client(monkeypatch):
    from ada.web.application.generic import activity

    calls = []
    class Client:
        def __init__(self, endpoint, **kwargs):
            calls.append(('init', endpoint, kwargs))
        def get_database_client(self, name):
            calls.append(('database', name))
            return self
        def get_container_client(self, name):
            calls.append(('container', name))
            return SimpleNamespace()
        def close(self):
            calls.append(('closed',))

    monkeypatch.setattr(activity, 'AzureCosmosClient', Client)
    settings = SimpleNamespace(
        endpoint='https://example.test', key='secret', database_name='app',
        connection_timeout_seconds=10, request_timeout_seconds=20,
    )
    with open_durable_activity_repository(settings=settings, container_name='users-activity') as repo:
        assert isinstance(repo, CosmosUserActivityRepository)
        assert calls[1:] == [('database', 'app'), ('container', 'users-activity')]
    assert calls[-1] == ('closed',)
    assert calls[0][2]['retry_write'] == 0
