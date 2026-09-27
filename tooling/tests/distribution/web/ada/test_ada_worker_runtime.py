from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_RUNTIME = (
    Path(__file__).resolve().parents[4]
    / 'distribution/web/starter/ada/src/application/runtime.py'
)


def _load_runtime(monkeypatch, *, environment: str, provider: str):
    calls = []
    closed = []
    local = SimpleNamespace(is_local=environment == 'local', is_production=environment == 'production')

    class IdentityConfigurationError(RuntimeError):
        pass

    class IdentityProvider:
        production_ready = True

        def validate_configuration(self):
            calls.append('validated')

    def module(name, **members):
        parts = name.split('.')
        for index in range(1, len(parts)):
            parent = '.'.join(parts[:index])
            if parent not in sys.modules:
                package = ModuleType(parent)
                package.__path__ = []
                monkeypatch.setitem(sys.modules, parent, package)
        obj = ModuleType(name)
        obj.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, obj)
        return obj

    @contextmanager
    def durable_stores(_settings):
        calls.append('durable-open')
        try:
            yield SimpleNamespace(stores='durable-stores')
        finally:
            closed.append('durable-close')

    def bootstrap(**kwargs):
        calls.append(('bootstrap', kwargs))
        return SimpleNamespace(server=lambda *_args: [], dash='dash-runtime')

    module(
        'ada.web.application.configuration_manager.local_runtime',
        create_local_configuration_manager_stores=lambda: 'local-stores',
    )
    module(
        'ada.web.application.generic.bootstrap',
        create_operational_application_runtime=bootstrap,
    )
    module(
        'ada.web.application.generic.host',
        run_operational_application=lambda **kwargs: calls.append(('non-docker', kwargs)),
    )
    module(
        'ada.web.application.generic.manager_deployment',
        ManagerStartupOptions=lambda: SimpleNamespace(provider=provider),
        open_durable_manager=durable_stores,
    )
    module(
        'ada.web.application.generic.settings',
        AdaGenericSettings=lambda: SimpleNamespace(environment=local),
    )
    module('application.composition', create_composition=lambda *_args: 'composition')
    production = module('application.production', create_identity_provider=lambda: IdentityProvider())
    module('atlanticus.web.dash_worker', prepare_dash_worker=lambda dash: calls.append(('dash-ready', dash)))
    module('atlanticus.web.identity.errors', IdentityConfigurationError=IdentityConfigurationError)
    module('atlanticus.web.identity.provider', IdentityProvider=IdentityProvider)
    module('atlanticus.web.identity.local', LocalIdentityProvider=lambda **kwargs: 'local-identity')
    module('atlanticus.web.models', WebApplicationRuntime=object)
    module('atlanticus.web.users.local', select_local_user=lambda: SimpleNamespace(subject_id='local'))
    spec = importlib.util.spec_from_file_location('test_ada_worker_runtime_source', _RUNTIME)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded, production, calls, closed, IdentityConfigurationError


def test_local_mode_uses_local_identity_without_loading_production_provider(monkeypatch):
    runtime, production, calls, closed, _error = _load_runtime(
        monkeypatch, environment='local', provider='durable'
    )
    production.create_identity_provider = lambda: pytest.fail('Production identity used locally')
    worker = runtime.create_worker_runtime()
    assert calls[0] == 'durable-open'
    assert calls[1][1]['identity_provider'] == 'local-identity'
    assert calls[1][1]['manager_stores'] == 'durable-stores'
    assert calls[2] == ('dash-ready', 'dash-runtime')
    worker.close()
    assert closed == ['durable-close']


def test_production_requires_durable_and_never_falls_back_to_local(monkeypatch):
    runtime, _production, _calls, _closed, error = _load_runtime(
        monkeypatch, environment='production', provider='auto'
    )
    with pytest.raises(error, match='durable Manager'):
        runtime.create_worker_runtime()


def test_production_uses_only_host_provider_and_closes_resources(monkeypatch):
    runtime, _production, calls, closed, _error = _load_runtime(
        monkeypatch, environment='production', provider='durable'
    )
    runtime._local_identity = lambda: pytest.fail('Local identity used in production')
    worker = runtime.create_worker_runtime()
    assert calls[:2] == ['validated', 'durable-open']
    assert isinstance(calls[2][1]['identity_provider'], sys.modules[
        'atlanticus.web.identity.provider'
    ].IdentityProvider)
    assert calls[3] == ('dash-ready', 'dash-runtime')
    worker.close()
    assert closed == ['durable-close']


def test_worker_closes_durable_resources_if_bootstrap_fails(monkeypatch):
    runtime, _production, _calls, closed, _error = _load_runtime(
        monkeypatch, environment='local', provider='durable'
    )
    runtime.create_operational_application_runtime = lambda **_kw: (_ for _ in ()).throw(
        RuntimeError('bootstrap failed')
    )
    with pytest.raises(RuntimeError, match='bootstrap failed'):
        runtime.create_worker_runtime()
    assert closed == ['durable-close']


def test_worker_closes_durable_resources_if_dash_preparation_fails(monkeypatch):
    runtime, _production, calls, closed, _error = _load_runtime(
        monkeypatch, environment='local', provider='durable'
    )

    def fail(_dash):
        raise RuntimeError('Dash assets unavailable')

    runtime.prepare_dash_worker = fail
    with pytest.raises(RuntimeError, match='Dash assets unavailable'):
        runtime.create_worker_runtime()

    assert calls[0] == 'durable-open'
    assert closed == ['durable-close']
