from __future__ import annotations

import pytest

from ada.web.inspection.core import (
    KpiDefinition,
    KpiDefinitionSnapshot,
    KpiDefinitionSnapshotStore,
)
from ada.web.inspection.runtime import KpiDefinitionWarmup


def _definition(kpi_key: str, title: str) -> KpiDefinition:
    return KpiDefinition(kpi_key=kpi_key, fields={'title': title})


def _snapshot(*definitions: KpiDefinition) -> KpiDefinitionSnapshot:
    return KpiDefinitionSnapshot(definitions=definitions)


class InMemoryProvider:
    def __init__(self, snapshot: KpiDefinitionSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def load_snapshot(self) -> KpiDefinitionSnapshot:
        self.calls += 1
        return self.snapshot


class FailingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def load_snapshot(self) -> KpiDefinitionSnapshot:
        self.calls += 1
        raise RuntimeError('Definition provider is unavailable')


def test_warmup_loads_complete_snapshot_through_injected_provider() -> None:
    transported = _definition('transported_total', 'Transportado')
    availability = _definition('availability', 'Disponibilidad')
    provider = InMemoryProvider(_snapshot(transported, availability))
    store = KpiDefinitionSnapshotStore()

    loaded = KpiDefinitionWarmup(provider, store).run()

    assert provider.calls == 1
    assert loaded is provider.snapshot
    assert store.get('transported_total') is transported
    assert store.get('availability') is availability


def test_failed_warmup_preserves_last_valid_snapshot() -> None:
    existing = _definition('transported_total', 'Anterior')
    store = KpiDefinitionSnapshotStore(_snapshot(existing))
    provider = FailingProvider()

    with pytest.raises(RuntimeError, match='Definition provider is unavailable'):
        KpiDefinitionWarmup(provider, store).run()

    assert provider.calls == 1
    assert store.get('transported_total') is existing


def test_invalid_provider_payload_preserves_last_valid_snapshot() -> None:
    existing = _definition('transported_total', 'Anterior')
    store = KpiDefinitionSnapshotStore(_snapshot(existing))

    class InvalidProvider:
        def load_snapshot(self) -> KpiDefinitionSnapshot:
            return None  # type: ignore[return-value]

    with pytest.raises(TypeError, match='Snapshot must be a KpiDefinitionSnapshot'):
        KpiDefinitionWarmup(InvalidProvider(), store).run()

    assert store.get('transported_total') is existing


def test_empty_startup_store_remains_empty_when_warmup_fails() -> None:
    store = KpiDefinitionSnapshotStore()

    with pytest.raises(RuntimeError, match='Definition provider is unavailable'):
        KpiDefinitionWarmup(FailingProvider(), store).run()

    assert store.get('transported_total') is None


def test_warmup_instances_keep_worker_local_stores_isolated() -> None:
    first_store = KpiDefinitionSnapshotStore()
    second_store = KpiDefinitionSnapshotStore()
    first = _definition('transported_total', 'Worker A')
    second = _definition('transported_total', 'Worker B')

    KpiDefinitionWarmup(InMemoryProvider(_snapshot(first)), first_store).run()
    KpiDefinitionWarmup(InMemoryProvider(_snapshot(second)), second_store).run()

    assert first_store.get('transported_total') is first
    assert second_store.get('transported_total') is second


def test_warmup_has_no_remote_fallback_on_lookup_after_initial_load() -> None:
    transported = _definition('transported_total', 'Transportado')
    provider = InMemoryProvider(_snapshot(transported))
    store = KpiDefinitionSnapshotStore()
    warmup = KpiDefinitionWarmup(provider, store)

    warmup.run()
    assert store.get('missing_kpi') is None
    assert store.get('missing_kpi') is None

    assert provider.calls == 1
