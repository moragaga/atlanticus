from __future__ import annotations

import threading
import time
from collections import Counter

import pytest

from ada_command_center.processes.alarms_delivery.parallel import (
    CosmosDispatchTask,
    ParallelCosmosPublisher,
)


class _Writer:
    def __init__(self, settings, counters, lock, delay=0.01, fail=False):
        self._settings = settings
        self._counters = counters
        self._lock = lock
        self._delay = delay
        self._fail = fail

    def __enter__(self):
        with self._lock:
            self._counters['active'] += 1
            self._counters['maximum'] = max(
                self._counters['maximum'], self._counters['active']
            )
            self._counters['opened'] += 1
        return self

    def upsert_item(self, *, container_name, item):
        time.sleep(self._delay)
        if self._fail:
            raise RuntimeError('simulated failure')
        with self._lock:
            self._counters['published'] += 1
        return item

    def __exit__(self, *_):
        with self._lock:
            self._counters['active'] -= 1
            self._counters['closed'] += 1


def _tasks(count):
    return tuple(
        CosmosDispatchTask(
            tool_key=f'tool-{index}',
            connection_ref=f'cosmos-{index}',
            container_name='live',
            documents=({'id': f'id-{index}', 'partition_key': f'tool-{index}'},),
        )
        for index in range(count)
    )


def test_bounded_parallelism_and_independent_client_lifetimes():
    counters = Counter()
    lock = threading.Lock()
    tasks = _tasks(8)
    connections = {task.connection_ref: task.connection_ref for task in tasks}
    authority_checks = []
    with ParallelCosmosPublisher(
        connections=connections,
        max_workers=2,
        client_factory=lambda settings: _Writer(settings, counters, lock),
    ) as publisher:
        result = publisher.publish(tasks, assert_authority=lambda: authority_checks.append(1))
    assert len(result) == 8
    assert all(item.successful and item.published_documents == 1 for item in result)
    assert counters['maximum'] == 2
    assert counters['opened'] == counters['closed'] == 8
    assert len(authority_checks) == 2


def test_partial_failure_is_returned_per_tool_and_clients_close():
    counters = Counter()
    lock = threading.Lock()
    tasks = _tasks(3)
    with ParallelCosmosPublisher(
        connections={task.connection_ref: task.connection_ref for task in tasks},
        max_workers=2,
        client_factory=lambda settings: _Writer(
            settings, counters, lock, fail=settings == 'cosmos-1'
        ),
    ) as publisher:
        result = publisher.publish(tasks, assert_authority=lambda: None)
    assert [item.successful for item in result] == [True, False, True]
    assert result[1].error_type == 'RuntimeError'
    assert counters['closed'] == 3


def test_unknown_connection_and_duplicate_tool_fail_before_writes():
    tasks = _tasks(2)
    with ParallelCosmosPublisher(
        connections={'cosmos-0': object()}, max_workers=2, client_factory=lambda _: None
    ) as publisher:
        with pytest.raises(ValueError, match='unknown'):
            publisher.publish(tasks, assert_authority=lambda: None)
        with pytest.raises(ValueError, match='per tool'):
            publisher.publish((tasks[0], tasks[0]), assert_authority=lambda: None)


def test_authority_failure_prevents_dispatch():
    tasks = _tasks(1)
    counters = Counter()
    lock = threading.Lock()
    with ParallelCosmosPublisher(
        connections={'cosmos-0': object()},
        max_workers=2,
        client_factory=lambda settings: _Writer(settings, counters, lock),
    ) as publisher:
        with pytest.raises(RuntimeError, match='expired'):
            publisher.publish(
                tasks,
                assert_authority=lambda: (_ for _ in ()).throw(RuntimeError('expired')),
            )
    assert counters['opened'] == 0
