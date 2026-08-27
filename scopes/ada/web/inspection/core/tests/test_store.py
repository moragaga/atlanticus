from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot, KpiDefinitionSnapshotStore


def _definition(kpi_key: str, title: str) -> KpiDefinition:
    return KpiDefinition(kpi_key=kpi_key, fields={'title': title})


def _snapshot(*definitions: KpiDefinition) -> KpiDefinitionSnapshot:
    return KpiDefinitionSnapshot(definitions=definitions)


def test_store_resolves_existing_definition_by_kpi_key() -> None:
    transported = _definition('transported_total', 'Transportado')
    store = KpiDefinitionSnapshotStore(_snapshot(transported))

    assert store.get('transported_total') is transported


def test_store_returns_none_for_missing_kpi_without_side_effects() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot(_definition('transported_total', 'Transportado')))

    assert store.get('missing_kpi') is None
    assert store.get('missing_kpi') is None


def test_store_rejects_invalid_lookup_identity() -> None:
    store = KpiDefinitionSnapshotStore()

    with pytest.raises(ValueError, match='KPI key must be a non-empty string'):
        store.get(' ')


def test_replace_removes_old_definitions_and_publishes_new_snapshot() -> None:
    old_definition = _definition('old_kpi', 'Old')
    new_definition = _definition('new_kpi', 'New')
    store = KpiDefinitionSnapshotStore(_snapshot(old_definition))

    store.replace(_snapshot(new_definition))

    assert store.get('old_kpi') is None
    assert store.get('new_kpi') is new_definition


def test_failed_replace_keeps_last_valid_snapshot() -> None:
    definition = _definition('transported_total', 'Transportado')
    store = KpiDefinitionSnapshotStore(_snapshot(definition))

    with pytest.raises(TypeError, match='Snapshot must be a KpiDefinitionSnapshot'):
        store.replace(None)  # type: ignore[arg-type]

    assert store.get('transported_total') is definition


def test_concurrent_lookup_observes_only_complete_old_or_new_definition() -> None:
    old_definition = _definition('transported_total', 'Old')
    new_definition = _definition('transported_total', 'New')
    old_snapshot = _snapshot(old_definition)
    new_snapshot = _snapshot(new_definition)
    store = KpiDefinitionSnapshotStore(old_snapshot)

    def replace_repeatedly() -> None:
        for _ in range(2_000):
            store.replace(new_snapshot)
            store.replace(old_snapshot)

    def read_repeatedly() -> set[str | None]:
        observed: set[str | None] = set()
        for _ in range(5_000):
            definition = store.get('transported_total')
            observed.add(None if definition is None else definition.fields['title'])
        return observed

    with ThreadPoolExecutor(max_workers=5) as executor:
        writer = executor.submit(replace_repeatedly)
        readers = [executor.submit(read_repeatedly) for _ in range(4)]
        writer.result()
        observed = set().union(*(reader.result() for reader in readers))

    assert observed
    assert observed <= {'Old', 'New'}
