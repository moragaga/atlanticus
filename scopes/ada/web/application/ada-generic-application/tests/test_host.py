from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from ada.web.application.generic import __main__ as cli, host
from ada.web.application.generic.settings import AdaPersistenceMode
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.users.local import LOCAL_USERS


def _environment(value: str) -> WebEnvironment:
    return WebEnvironment(value)


def _local_settings(tmp_path):
    return SimpleNamespace(
        persistence_mode=AdaPersistenceMode.LOCAL,
        environment=_environment('local'),
        azure_observability_mode='off',
        azure_observability_profile='slim',
        application_insights_connection_string=None,
    )


def test_local_host_owns_runtime(tmp_path, monkeypatch) -> None:
    settings = _local_settings(tmp_path)
    calls = []
    application = SimpleNamespace(dash='dash', server='server')

    def extension_factory(*_args):
        return None

    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: settings)
    monkeypatch.setattr(host, 'create_local_configuration_manager_stores', lambda: 'local-stores')
    monkeypatch.setattr(host, '_local_identity', lambda: 'local-identity')

    def create(**kwargs):
        calls.append(kwargs)
        return application

    monkeypatch.setattr(host, 'create_operational_application_runtime', create)
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda dash: calls.append({'dash': dash}))

    worker = host.create_worker_runtime(extension_factory=extension_factory)

    assert worker.application is application
    assert calls[0]['manager_stores'] == 'local-stores'
    assert calls[0]['identity_provider'] == 'local-identity'
    assert calls[0]['manager_source_name'] == 'Local Source'
    assert calls[0]['manager_projection_name'] == 'Local Projection'
    assert calls[0]['activity_repository'] is not None
    assert calls[0]['extension_factory'] is extension_factory
    assert calls[1] == {'dash': 'dash'}
    worker.close()


@pytest.mark.parametrize('local_user', LOCAL_USERS, ids=('jane', 'john'))
def test_local_host_uses_automatic_identity_when_override_is_unset(
    tmp_path, monkeypatch, local_user
) -> None:
    captured = {}
    application = SimpleNamespace(dash='dash', server='server')
    monkeypatch.delenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', raising=False)
    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: _local_settings(tmp_path))
    monkeypatch.setattr(host, 'create_local_configuration_manager_stores', lambda: 'local-stores')
    monkeypatch.setattr(host, 'select_local_user', lambda: local_user)
    monkeypatch.setattr(
        host,
        'create_operational_application_runtime',
        lambda **kwargs: captured.update(kwargs) or application,
    )
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda _dash: None)

    worker = host.create_worker_runtime()

    identity = captured['identity_provider'].resolve(None)
    assert identity.subject_id == local_user.subject_id
    worker.close()


def test_local_host_uses_explicit_identity_override(tmp_path, monkeypatch) -> None:
    captured = {}
    application = SimpleNamespace(dash='dash', server='server')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:john-doe')
    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: _local_settings(tmp_path))
    monkeypatch.setattr(host, 'create_local_configuration_manager_stores', lambda: 'local-stores')
    monkeypatch.setattr(
        host,
        'select_local_user',
        lambda: pytest.fail('Explicit local identity must bypass automatic selection'),
    )
    monkeypatch.setattr(
        host,
        'create_operational_application_runtime',
        lambda **kwargs: captured.update(kwargs) or application,
    )
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda _dash: None)

    worker = host.create_worker_runtime()

    identity = captured['identity_provider'].resolve(None)
    assert identity.subject_id == 'local:john-doe'
    worker.close()


def test_durable_local_host_keeps_resources_open(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(
        persistence_mode=AdaPersistenceMode.DURABLE,
        environment=_environment('local'),
        azure_observability_mode='off',
        azure_observability_profile='slim',
        application_insights_connection_string=None,
    )
    deployment = SimpleNamespace(
        stores='durable-stores',
        activity_resource=SimpleNamespace(connection_ref='ada-cosmos', physical_name='users-activity'),
        connections=SimpleNamespace(cosmos={'ada-cosmos': SimpleNamespace(settings='test-settings')}),
    )
    events = []
    captured = {}
    application = SimpleNamespace(dash='dash', server='server')

    @contextmanager
    def opened(_settings):
        events.append('opened')
        try:
            yield deployment
        finally:
            events.append('closed')

    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: settings)
    monkeypatch.setattr(host, 'open_durable_manager', opened)
    monkeypatch.setattr(host, '_local_identity', lambda: 'local-identity')
    @contextmanager
    def activity(*, settings, container_name):
        assert settings == 'test-settings'
        assert container_name == 'users-activity'
        events.append('activity-opened')
        try:
            yield 'activity-repository'
        finally:
            events.append('activity-closed')
    monkeypatch.setattr(host, 'open_durable_activity_repository', activity)

    monkeypatch.setattr(
        host,
        'create_operational_application_runtime',
        lambda **kwargs: captured.update(kwargs) or application,
    )
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda _dash: None)

    worker = host.create_worker_runtime()

    assert events == ['opened', 'activity-opened']
    assert captured['manager_stores'] == 'durable-stores'
    assert captured['activity_repository'] == 'activity-repository'
    assert captured['identity_provider'] == 'local-identity'
    assert captured['manager_source_name'] == 'Blob Storage'
    assert captured['manager_projection_name'] == 'Cosmos DB'
    worker.close()
    assert events == ['opened', 'activity-opened', 'activity-closed', 'closed']


def test_production_host_requires_injected_identity(monkeypatch) -> None:
    settings = SimpleNamespace(
        persistence_mode=AdaPersistenceMode.DURABLE,
        environment=_environment('production'),
        azure_observability_mode='off',
        azure_observability_profile='slim',
        application_insights_connection_string=None,
    )
    deployment = SimpleNamespace(
        stores='stores',
    )

    @contextmanager
    def opened(_settings):
        yield deployment

    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: settings)
    monkeypatch.setattr(host, 'open_durable_manager', opened)

    with pytest.raises(Exception, match='production identity provider'):
        host.create_worker_runtime()


def test_run_closes_worker_after_server_failure(monkeypatch) -> None:
    events = []
    worker = SimpleNamespace(
        application=object(),
        close=lambda: events.append('closed'),
    )
    monkeypatch.setattr(host, 'create_worker_runtime', lambda **_kwargs: worker)
    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: SimpleNamespace(web_port=8000))

    def failed(_application, *, port):
        assert port == 8000
        raise RuntimeError('stop')

    monkeypatch.setattr(host, 'run_web_application', failed)

    with pytest.raises(RuntimeError, match='stop'):
        host.run_operational_application()

    assert events == ['closed']


def test_cli_main_delegates_to_host(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        cli,
        'run_operational_application',
        lambda: calls.append('run'),
    )

    cli.main()

    assert calls == ['run']
