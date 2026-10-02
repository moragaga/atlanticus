from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from ada.web.application.generic import __main__ as cli, host
from ada.web.application.generic.settings import AdaPersistenceMode
from atlanticus.web.users.local import LOCAL_USERS


def _environment(value: str):
    return SimpleNamespace(
        is_local=value == 'local',
        is_production=value == 'production',
    )


def _local_settings(tmp_path):
    return SimpleNamespace(
        persistence_mode=AdaPersistenceMode.LOCAL,
        environment=_environment('local'),
        master_projection_local_path=lambda: (tmp_path / 'material.zip').resolve(),
    )


def test_local_host_owns_runtime_and_master_projection(tmp_path, monkeypatch) -> None:
    settings = _local_settings(tmp_path)
    calls = []
    reader = object()
    application = SimpleNamespace(dash='dash', server='server')

    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: settings)
    monkeypatch.setattr(host, 'create_local_configuration_manager_stores', lambda: 'local-stores')
    monkeypatch.setattr(host, '_local_identity', lambda: 'local-identity')
    monkeypatch.setattr(host, 'LocalMasterMaterialReader', lambda path: reader)

    def create(**kwargs):
        calls.append(kwargs)
        return application

    monkeypatch.setattr(host, 'create_operational_application_runtime', create)
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda dash: calls.append({'dash': dash}))

    worker = host.create_worker_runtime(composition_factory=lambda *_args: None)

    assert worker.application is application
    assert calls[0]['manager_stores'] == 'local-stores'
    assert calls[0]['identity_provider'] == 'local-identity'
    assert calls[0]['manager_source_name'] == 'Local Source'
    assert calls[0]['manager_projection_name'] == 'Local Projection'
    assert calls[0]['master_material_reader'] is reader
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
    monkeypatch.setattr(host, 'LocalMasterMaterialReader', lambda _path: object())
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
    monkeypatch.setattr(host, 'LocalMasterMaterialReader', lambda _path: object())
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


def test_durable_local_host_keeps_resources_open_and_uses_durable_names(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(
        persistence_mode=AdaPersistenceMode.DURABLE,
        environment=_environment('local'),
        master_projection_blob_name=lambda: 'app/master-projection/material.zip',
    )
    resource = SimpleNamespace(connection_ref='storage', container_name='configuration')
    deployment = SimpleNamespace(
        stores='durable-stores',
        resources=SimpleNamespace(application_source=resource),
        connections=SimpleNamespace(storage={'storage': object()}),
    )
    events = []
    captured = {}
    reader = object()
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
    monkeypatch.setattr(host, 'BlobMasterMaterialReader', lambda **_kwargs: reader)
    monkeypatch.setattr(
        host,
        'create_operational_application_runtime',
        lambda **kwargs: captured.update(kwargs) or application,
    )
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda _dash: None)

    worker = host.create_worker_runtime()

    assert events == ['opened']
    assert captured['manager_stores'] == 'durable-stores'
    assert captured['identity_provider'] == 'local-identity'
    assert captured['manager_source_name'] == 'Blob Storage'
    assert captured['manager_projection_name'] == 'Cosmos DB'
    assert captured['master_material_reader'] is reader
    worker.close()
    assert events == ['opened', 'closed']


def test_production_host_requires_injected_identity(monkeypatch) -> None:
    settings = SimpleNamespace(
        persistence_mode=AdaPersistenceMode.DURABLE,
        environment=_environment('production'),
        master_projection_blob_name=lambda: 'app/master-projection/material.zip',
    )
    resource = SimpleNamespace(connection_ref='storage', container_name='configuration')
    deployment = SimpleNamespace(
        stores='stores',
        resources=SimpleNamespace(application_source=resource),
        connections=SimpleNamespace(storage={'storage': object()}),
    )

    @contextmanager
    def opened(_settings):
        yield deployment

    monkeypatch.setattr(host, 'AdaGenericSettings', lambda: settings)
    monkeypatch.setattr(host, 'open_durable_manager', opened)
    monkeypatch.setattr(host, 'BlobMasterMaterialReader', lambda **_kwargs: object())

    with pytest.raises(Exception, match='production identity provider'):
        host.create_worker_runtime()


def test_run_closes_worker_after_server_failure(monkeypatch) -> None:
    events = []
    worker = SimpleNamespace(
        application=object(),
        close=lambda: events.append('closed'),
    )
    monkeypatch.setattr(host, 'create_worker_runtime', lambda **_kwargs: worker)

    def failed(_application):
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


def test_host_commented_mirror_is_ast_equivalent() -> None:
    import ast

    package_root = Path(host.__file__).resolve().parents[5]
    productive = Path(host.__file__).read_text(encoding='utf-8')
    commented = (package_root / 'commented/ada/web/application/generic/host.py').read_text(
        encoding='utf-8'
    )
    assert ast.dump(ast.parse(productive), include_attributes=False) == ast.dump(
        ast.parse(commented), include_attributes=False
    )
