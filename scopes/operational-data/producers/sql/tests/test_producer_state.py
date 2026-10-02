from datetime import UTC, datetime

from atlanticus.data_producers.sql import SqlProducerState
from atlanticus.state import AtomicStateStore, StateKey


def test_state_uses_configured_producer_namespace_and_tracks_our_timestamps(tmp_path) -> None:
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    store = AtomicStateStore(volume_path=tmp_path, application='app')
    state = SqlProducerState(store=store, producer_key='producer', clock=lambda: now)

    committed = state.commit_source(
        source_key='source_a',
        target_scope_token='scope',
        changed=True,
        source_last_update_utc=None,
        publication_signatures={'dataset': 'signature'},
    )

    assert committed.revision == 1
    assert committed.last_synced_at_utc == now
    assert committed.last_change_at_utc == now
    assert store.path_for(StateKey(namespace=('producers', 'producer'), name='source_a')).exists()


def test_unchanged_source_advances_sync_without_advancing_change(tmp_path) -> None:
    moments = iter(
        (
            datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
            datetime(2026, 10, 2, 12, 1, tzinfo=UTC),
        )
    )
    state = SqlProducerState(
        store=AtomicStateStore(volume_path=tmp_path, application='app'),
        producer_key='producer',
        clock=lambda: next(moments),
    )

    first = state.commit_source(
        source_key='source',
        target_scope_token=None,
        changed=True,
        source_last_update_utc=None,
        publication_signatures={'dataset': 'same'},
    )
    second = state.commit_source(
        source_key='source',
        target_scope_token=None,
        changed=False,
        source_last_update_utc=None,
        publication_signatures={'dataset': 'same'},
    )

    assert second.revision == first.revision == 1
    assert second.last_synced_at_utc == datetime(2026, 10, 2, 12, 1, tzinfo=UTC)
    assert second.last_change_at_utc == datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def test_signature_recovers_commit_before_state(tmp_path) -> None:
    state = SqlProducerState(
        store=AtomicStateStore(volume_path=tmp_path, application='app'),
        producer_key='producer',
    )

    recovered = state.commit_source(
        source_key='source',
        target_scope_token=None,
        changed=False,
        source_last_update_utc=None,
        publication_signatures={'dataset': 'already-published'},
    )

    assert recovered.revision == 1


def test_existing_state_ignores_retired_source_change_marker(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='app')
    key = StateKey(namespace=('producers', 'producer'), name='source')
    store.replace(
        key,
        {
            'producer': 'producer',
            'source_key': 'source',
            'revision': 2,
            'source_change_marker': {
                'source_table': 'dbo.source',
                'generation_token': 'legacy',
                'last_user_update_token': 'legacy-update',
                'user_updates': 10,
            },
            'source_scope_token': '1|2',
            'source_last_update_utc': None,
            'last_synced_at_utc': '2026-10-02T11:00:00.000000Z',
            'last_change_at_utc': '2026-10-02T10:00:00.000000Z',
            'publication_signatures': {'dataset': 'signature'},
        },
    )

    state = SqlProducerState(store=store, producer_key='producer').source_state('source')

    assert state.revision == 2
    assert state.source_scope_token == '1|2'
    assert state.last_synced_at_utc == datetime(2026, 10, 2, 11, 0, tzinfo=UTC)
    assert not hasattr(state, 'source_change_marker')
