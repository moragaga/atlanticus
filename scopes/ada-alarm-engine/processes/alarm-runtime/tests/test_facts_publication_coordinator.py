from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ada.processes.alarm_runtime.publication import operational as publications


@dataclass
class _Head:
    durable: str | None
    aligned: bool = True


class _Persistence:
    def __init__(self):
        self.head = _Head('C0')

    def read_head(self):
        return self.head

    def read_effective_head(self):
        return SimpleNamespace()


class _Facts:
    root = None
    source_key = 'a'

    def __init__(self):
        self.initialized = 0
        self.published = 0
        self.fail = False

    def initialize_if_needed(self, **kwargs):
        self.initialized += 1
        return True

    def publish_unexported(self, **kwargs):
        if self.fail:
            self.fail = False
            raise OSError('FACTS interrupted')
        self.published += 1
        return 1


class _Current:
    root = None
    source_key = 'a'

    def __init__(self):
        self.published = 0

    def publish(self, **kwargs):
        self.published += 1
        return True


class _Context:
    def assert_lease_current(self):
        return None


@pytest.fixture(autouse=True)
def _protocol_stubs(monkeypatch):
    monkeypatch.setattr(publications, 'AlarmPersistence', _Persistence)
    monkeypatch.setattr(publications, 'AlarmCommittedFactsExporter', _Facts)
    monkeypatch.setattr(publications, 'AlarmDurableCurrentPublisher', _Current)


def test_current_remains_fresh_when_facts_publication_is_deferred():
    persistence, facts, current = _Persistence(), _Facts(), _Current()
    coordinator = publications.AlarmDurablePublications(persistence, facts, current)
    context = _Context()
    assert coordinator.reconcile(context, publish_facts=False)
    assert current.published == 1
    assert facts.published == 0
    persistence.head = _Head('C1')
    assert coordinator.reconcile(context, publish_facts=False)
    assert current.published == 2
    assert facts.published == 0
    assert coordinator.reconcile(context, publish_facts=True)
    assert current.published == 2
    assert facts.published == 1
    assert not coordinator.reconcile(context, publish_facts=True)
    assert facts.published == 1


def test_failed_facts_export_remains_due_for_retry():
    persistence, facts, current = _Persistence(), _Facts(), _Current()
    coordinator = publications.AlarmDurablePublications(persistence, facts, current)
    context = _Context()
    assert coordinator.reconcile(context, publish_facts=False)
    facts.fail = True
    with pytest.raises(OSError, match='FACTS interrupted'):
        coordinator.reconcile(context, publish_facts=True)
    assert coordinator.reconcile(context, publish_facts=True)
    assert facts.published == 1
    assert current.published == 1
