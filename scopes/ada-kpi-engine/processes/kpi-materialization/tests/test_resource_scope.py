from __future__ import annotations

from types import SimpleNamespace

import pytest

import ada.processes.kpi_materialization.composition as composition_module
from ada.processes.kpi_materialization.composition import build_composition
from ada.processes.kpi_materialization.job import READINESS_RETRY_SECONDS
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment


def _configuration(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-materialization-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'POLL_INTERVAL_SECONDS': str(READINESS_RETRY_SECONDS),
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def _connection():
    return CosmosSettings(
        endpoint='http://localhost:8081',
        database_name='ada-test',
        key='local-test-key',
        allow_insecure_http=True,
    )


def test_materialization_runs_once_and_closes_cosmos_before_lease_release(
    tmp_path, monkeypatch
):
    composition = build_composition(
        configuration=_configuration(tmp_path),
        connections={'tool_a': _connection()},
    )
    events = []
    lease = SimpleNamespace(active=False)
    client = composition.clients['tool_a']

    def close():
        assert lease.active
        events.append('close')

    monkeypatch.setattr(client, 'close', close)

    def fake_execute_job(*, definition, iteration, resource_scope, argv, environ):
        assert definition.run_once is True
        assert definition.poll_interval_seconds == 0
        assert definition.job_key == 'kpi-materialization'
        assert iteration == composition.job.run_iteration
        assert argv == ('--run-once',)
        assert environ == composition.configuration.values
        assert events == []
        lease.active = True
        context = SimpleNamespace(assert_lease_current=lambda: events.append('authority'))
        with resource_scope(context):
            events.append('iteration')
            assert events == ['authority', 'iteration']
        lease.active = False
        events.append('release')
        return 'completed'

    monkeypatch.setattr(composition_module, 'execute_job', fake_execute_job)

    assert composition.execute(argv=('--run-once',)) == 'completed'
    assert events == ['authority', 'iteration', 'close', 'release']


def test_resource_scope_closes_cosmos_after_iteration_error(tmp_path, monkeypatch):
    composition = build_composition(
        configuration=_configuration(tmp_path),
        connections={'tool_a': _connection()},
    )
    closed = []
    monkeypatch.setattr(composition.clients['tool_a'], 'close', lambda: closed.append(True))

    def fake_execute_job(*, resource_scope, **_):
        context = SimpleNamespace(assert_lease_current=lambda: None)
        with resource_scope(context):
            raise RuntimeError('simulated iteration failure')

    monkeypatch.setattr(composition_module, 'execute_job', fake_execute_job)
    with pytest.raises(RuntimeError, match='simulated iteration failure'):
        composition.execute(argv=('--run-once',))
    assert closed == [True]
