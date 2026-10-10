from __future__ import annotations

from contextlib import contextmanager

from ada.alarms.persistence.operational.incremental import IncrementalAlarmPersistence

from .support import mutation_fence
from .test_recovery_checkpoint import _compacted_store


def test_compaction_uses_single_nonreentrant_authority_fence(tmp_path) -> None:
    store = _compacted_store(tmp_path)
    snapshots_before = {item.priority_group: item.as_document() for item in store.list_snapshots()}
    fence_held = False
    independent_checks = 0

    def assert_authority() -> None:
        nonlocal independent_checks
        if fence_held:
            raise AssertionError('authority was reacquired inside the mutation fence')
        independent_checks += 1

    @contextmanager
    def fenced_mutation():
        nonlocal fence_held
        if fence_held:
            raise AssertionError('mutation fence is not reentrant')
        fence_held = True
        try:
            yield
        finally:
            fence_held = False

    removed = store.compact_recovered_wal(
        exported_through=store.read_head().durable,
        assert_authority=assert_authority,
        fenced_mutation=fenced_mutation,
    )

    assert removed > 0
    assert independent_checks == 1
    assert not fence_held
    restarted = IncrementalAlarmPersistence(application_root=tmp_path)
    restarted.recover(assert_authority=lambda: None, fenced_mutation=mutation_fence)
    assert {
        item.priority_group: item.as_document() for item in restarted.list_snapshots()
    } == snapshots_before
