from types import SimpleNamespace

import pytest

from atlanticus.data_producers.meteodata.errors import MeteodataAcquisitionError, MeteodataResponseError
from atlanticus.data_producers.meteodata.job import MeteodataJob


class Log:
    def warning(self, *args, **kwargs):
        pass


class Context:
    logger = Log()
    safe_remaining_seconds = 220

    def __init__(self):
        self.facts = {}
        self.waits = []
        self.work = False

    def raise_if_cancelled(self):
        pass

    def wait(self, seconds):
        self.waits.append(seconds)
        return True

    def set_iteration_fact(self, key, value):
        self.facts[key] = value

    def mark_iteration_work(self):
        self.work = True


class Acquirer:
    def __init__(self, *, fail_projection=False, fail_data=False):
        self.calls = 0
        self.fail_projection = fail_projection
        self.fail_data = fail_data

    def acquire_projection(self):
        if self.fail_projection:
            raise MeteodataResponseError('unexpected source projection')
        return SimpleNamespace()

    def acquire_data(self, **kwargs):
        self.calls += 1
        if self.fail_data:
            raise MeteodataAcquisitionError('all Meteodata measurement queries failed')
        return SimpleNamespace(measurements=(), failed_queries=())


class Materializer:
    def __init__(self, updates):
        self.updates = list(updates)

    def publish_projection(self, **kwargs):
        return True

    def publish_data(self, **kwargs):
        return self.updates.pop(0)


def test_no_new_data_triggers_only_one_interruptible_retry():
    acquirer = Acquirer()
    context = Context()
    job = MeteodataJob(
        acquirer=acquirer, materializer=Materializer([0, 2]),
        lookback_minutes=90, retry_delay_seconds=60,
    )
    job.run_iteration(context)
    assert acquirer.calls == 2
    assert context.waits == [60]
    assert context.facts['data_rows_updated'] == 2
    assert context.work


def test_failed_projection_does_not_block_data():
    acquirer = Acquirer(fail_projection=True)
    context = Context()
    MeteodataJob(
        acquirer=acquirer, materializer=Materializer([3]),
        lookback_minutes=90, retry_delay_seconds=60,
    ).run_iteration(context)
    assert context.facts['projection_failed'] is True
    assert context.facts['data_rows_updated'] == 3
    assert context.facts['outcome'] == 'partial'


def test_both_failed_streams_raise_explicit_error():
    job = MeteodataJob(
        acquirer=Acquirer(fail_projection=True, fail_data=True),
        materializer=Materializer([]), lookback_minutes=90, retry_delay_seconds=60,
    )
    with pytest.raises(MeteodataAcquisitionError, match='both'):
        job.run_iteration(Context())
