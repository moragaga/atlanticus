from __future__ import annotations

import threading
from collections import Counter

import pytest

from ada_command_center.processes.alarms_delivery.parallel import (
    ALARM_PROJECTION_CONTAINER_NAME,
    CosmosDispatchTask,
    ParallelCosmosPublisher,
)


class _Writer:
    def __init__(self, settings, counters, lock):
        self._settings = settings
        self._counters = counters
        self._lock = lock

    def __enter__(self):
        with self._lock:
            self._counters['opened'] += 1
        return self

    def upsert_item(self, *, container_name, item):
        with self._lock:
            self._counters['published'] += 1
            self._counters['containers'].append(container_name)
        return item

    def __exit__(self, *_):
        with self._lock:
            self._counters['closed'] += 1


def test_tools_publish_to_their_connections_and_fixed_container():
    counters = Counter()
    counters['containers'] = []
    lock = threading.Lock()
    shared_settings = object()
    tasks = (
        CosmosDispatchTask(
            tool_key='tool-a',
            documents=({'id': 'a'},),
        ),
        CosmosDispatchTask(
            tool_key='tool-b',
            documents=({'id': 'b'},),
        ),
    )
    with ParallelCosmosPublisher(
        connections={
            'tool-a': shared_settings,
            'tool-b': shared_settings,
        },
        max_workers=2,
        client_factory=lambda settings: _Writer(settings, counters, lock),
    ) as publisher:
        result = publisher.publish(tasks, assert_authority=lambda: None)
    assert all(item.successful for item in result)
    assert counters['published'] == 2
    assert counters['opened'] == counters['closed'] == 2
    assert counters['containers'] == [
        ALARM_PROJECTION_CONTAINER_NAME,
        ALARM_PROJECTION_CONTAINER_NAME,
    ]


def test_unknown_tool_fails_before_writes():
    task = CosmosDispatchTask(tool_key='tool-a', documents=({'id': 'a'},))
    with ParallelCosmosPublisher(
        connections={},
        max_workers=1,
        client_factory=lambda _: None,
    ) as publisher, pytest.raises(ValueError, match='unknown Tool'):
        publisher.publish((task,), assert_authority=lambda: None)
