from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

import atlanticus.runtime.context as context_module
from atlanticus.kernel import OperationStatus
from atlanticus.runtime import (
    ConcurrentExecutionError,
    JobDefinition,
    execute_job,
)


def _environment(tmp_path, *, disabled=False, scheduled=False):
    value = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'lifecycle-test',
        'VOLUMEN_PATH': str(tmp_path),
        'ATLANTICUS_JOB_EXECUTION_DISABLED': 'true' if disabled else 'false',
    }
    if scheduled:
        value['ATLANTICUS_JOB_SCHEDULE_CRON'] = '*/10 * * * *'
        value['ATLANTICUS_JOB_SCHEDULE_TIMEZONE'] = 'UTC'
    return value


def _definition(*, name='resource-lifecycle', scheduled=False):
    return JobDefinition(
        module_name='test_resource_lifecycle',
        service_name=name,
        job_key=name,
        run_once=True,
        iteration_timeout_seconds=4,
        execution_timeout_seconds=12,
        shutdown_grace_seconds=2,
        lease_timeout_seconds=6,
        lease_renew_seconds=1,
        lease_wait_seconds=0,
        lease_poll_seconds=0.05,
        resource_sample_seconds=0.05,
    )


def _lease_file(tmp_path, name='resource-lifecycle'):
    return tmp_path / 'lifecycle-test' / '.runtime' / 'leases' / f'{name}.json'


def _authority_file(tmp_path, name='resource-lifecycle'):
    return tmp_path / 'lifecycle-test' / '.runtime' / 'authority' / f'{name}.json'


def test_resource_scope_surrounds_recovery_iteration_drain_and_releases_after_close(tmp_path):
    events = []
    lease_path = _lease_file(tmp_path)

    @contextmanager
    def scope(context):
        events.append('resource_factory')
        context.assert_lease_current()
        assert context.lease_generation == 1
        assert lease_path.exists()
        events.append('open')
        try:
            yield
        finally:
            context.assert_lease_current()
            assert lease_path.exists()
            events.append('close')

    def recovery(context):
        context.assert_lease_current()
        events.append('recovery')

    def iteration(context):
        context.assert_lease_current()
        events.append('iteration')

    def drain(context):
        context.assert_lease_current()
        events.append('drain')

    result = execute_job(
        definition=_definition(),
        resource_scope=scope,
        recovery=recovery,
        iteration=iteration,
        drain=drain,
        argv=[],
        environ=_environment(tmp_path),
    )
    assert result.stop_reason == 'run_once'
    assert result.status is OperationStatus.SUCCESS
    assert events == ['resource_factory', 'open', 'recovery', 'iteration', 'drain', 'close']
    assert not lease_path.exists()


def test_resource_factory_is_not_called_when_execution_is_disabled(tmp_path):
    calls = []
    result = execute_job(
        definition=_definition(),
        resource_scope=lambda context: calls.append('factory'),
        iteration=lambda context: calls.append('iteration'),
        argv=[],
        environ=_environment(tmp_path, disabled=True),
    )
    assert result.stop_reason == 'execution_disabled'
    assert calls == []
    assert not _lease_file(tmp_path).exists()


def test_resource_factory_is_not_called_when_scheduled_slot_is_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        context_module,
        '_utc_now',
        lambda: datetime(2026, 10, 17, 10, 0, 5, tzinfo=UTC),
    )
    calls = []

    @contextmanager
    def scope(context):
        calls.append('open')
        yield
        calls.append('close')

    arguments = {
        'definition': _definition(),
        'resource_scope': scope,
        'iteration': lambda context: calls.append('iteration'),
        'argv': [],
        'environ': _environment(tmp_path, scheduled=True),
    }
    first = execute_job(**arguments)
    second = execute_job(**arguments)
    assert first.stop_reason == 'run_once'
    assert second.stop_reason == 'scheduled_slot_completed'
    assert calls == ['open', 'iteration', 'close']


def test_resource_factory_is_not_called_when_lease_is_owned_by_another_run(tmp_path):
    events = []

    @contextmanager
    def outer_scope(context):
        events.append('owner_open')
        yield
        events.append('owner_close')

    def owner_iteration(context):
        with pytest.raises(ConcurrentExecutionError):
            execute_job(
                definition=_definition(),
                resource_scope=lambda inner: events.append('successor_factory'),
                iteration=lambda inner: events.append('successor_iteration'),
                argv=[],
                environ=_environment(tmp_path),
            )
        events.append('owner_iteration')

    result = execute_job(
        definition=_definition(),
        resource_scope=outer_scope,
        iteration=owner_iteration,
        argv=[],
        environ=_environment(tmp_path),
    )
    assert result.stop_reason == 'run_once'
    assert events == ['owner_open', 'owner_iteration', 'owner_close']


@pytest.mark.parametrize('stage', ('factory', 'enter', 'recovery', 'iteration', 'drain', 'close'))
def test_resource_failure_releases_lease_and_does_not_complete_scheduled_slot(
    tmp_path, monkeypatch, stage,
):
    monkeypatch.setattr(
        context_module,
        '_utc_now',
        lambda: datetime(2026, 10, 17, 10, 0, 5, tzinfo=UTC),
    )
    calls = []
    lease_path = _lease_file(tmp_path)

    @contextmanager
    def scope(context):
        calls.append('open')
        context.assert_lease_current()
        assert lease_path.exists()
        if stage == 'enter':
            raise RuntimeError('failure: enter')
        try:
            yield
        finally:
            context.assert_lease_current()
            assert lease_path.exists()
            calls.append('close')
            if stage == 'close':
                raise RuntimeError('failure: close')

    def factory(context):
        calls.append('factory')
        if stage == 'factory':
            context.assert_lease_current()
            raise RuntimeError('failure: factory')
        return scope(context)

    def recovery(context):
        calls.append('recovery')
        if stage == 'recovery':
            raise RuntimeError('failure: recovery')

    def iteration(context):
        calls.append('iteration')
        if stage == 'iteration':
            raise RuntimeError('failure: iteration')

    def drain(context):
        calls.append('drain')
        if stage == 'drain':
            raise RuntimeError('failure: drain')

    with pytest.raises(RuntimeError, match=f'failure: {stage}'):
        execute_job(
            definition=_definition(),
            resource_scope=factory,
            recovery=recovery,
            iteration=iteration,
            drain=drain,
            argv=[],
            environ=_environment(tmp_path, scheduled=True),
        )
    assert not lease_path.exists()
    if stage in ('factory', 'enter'):
        assert 'close' not in calls
    else:
        assert 'close' in calls
    if stage == 'close':
        assert calls == ['factory', 'open', 'recovery', 'iteration', 'drain', 'close']

    @contextmanager
    def good_scope(context):
        context.assert_lease_current()
        assert lease_path.exists()
        yield
        context.assert_lease_current()

    subsequent = execute_job(
        definition=_definition(),
        resource_scope=good_scope,
        iteration=lambda context: context.assert_lease_current(),
        argv=[],
        environ=_environment(tmp_path, scheduled=True),
    )
    assert subsequent.status is OperationStatus.SUCCESS
    assert subsequent.stop_reason == 'run_once'
    assert not lease_path.exists()
    assert _authority_file(tmp_path).exists()


def test_non_callable_resource_scope_is_rejected(tmp_path):
    with pytest.raises(TypeError, match='resource_scope must be callable'):
        execute_job(
            definition=_definition(),
            resource_scope=object(),
            iteration=lambda context: None,
            argv=[],
            environ=_environment(tmp_path),
        )
    assert not _lease_file(tmp_path).exists()
