from datetime import UTC, datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from ada.web.time_status.store_adapter import (
    TimeStatusStoreAdapter,
    TimeStatusStoreContractError,
    TimeStatusStoreDocumentSource,
    TimeStatusTimestampQuality,
    TimeStatusToolScopeError,
    parse_time_status_store_document,
)


class InMemoryDocumentSource:
    def __init__(self, documents: dict[str, dict[str, object]]) -> None:
        self.documents = documents
        self.calls: list[str] = []

    def load_time_status_document(self, *, tool_key: str):
        self.calls.append(tool_key)
        return self.documents.get(tool_key)


def _document(*, tool_key: str = 'integrated_operations') -> dict[str, object]:
    return {
        'tool_key': tool_key,
        'generated_at_utc': '2026-08-28T22:00:05Z',
        'sources': {
            'pi': '2026-08-28T22:00:00Z',
            'dispatch': '2026-08-28T21:59:50-00:00',
            'blockgrade': '2026-08-28T21:59:40+00:00',
        },
    }


def test_adapter_loads_exact_tool_scope_and_preserves_extra_sources() -> None:
    source = InMemoryDocumentSource({'integrated_operations': _document()})
    adapter = TimeStatusStoreAdapter(source)

    snapshot = adapter.load_snapshot(tool_key='integrated_operations')

    assert isinstance(source, TimeStatusStoreDocumentSource)
    assert source.calls == ['integrated_operations']
    assert snapshot is not None
    assert snapshot.tool_key == 'integrated_operations'
    assert snapshot.generated_at_iso == '2026-08-28T22:00:05Z'
    assert tuple(snapshot.sources) == ('pi', 'dispatch', 'blockgrade')
    assert isinstance(snapshot.sources, MappingProxyType)
    assert snapshot.source('blockgrade').quality is TimeStatusTimestampQuality.VALID


def test_same_source_instance_keeps_tool_snapshots_isolated() -> None:
    source = InMemoryDocumentSource(
        {
            'integrated_operations': _document(tool_key='integrated_operations'),
            'process': {
                'tool_key': 'process',
                'generated_at_utc': '2026-08-28T22:01:05Z',
                'sources': {'pi': '2026-08-28T22:01:00Z'},
            },
        }
    )
    adapter = TimeStatusStoreAdapter(source)

    operations = adapter.load_snapshot(tool_key='integrated_operations')
    process = adapter.load_snapshot(tool_key='process')

    assert operations is not None and process is not None
    assert operations.tool_key == 'integrated_operations'
    assert process.tool_key == 'process'
    assert operations.source('dispatch').quality is TimeStatusTimestampQuality.VALID
    assert process.source('dispatch').quality is TimeStatusTimestampQuality.MISSING
    assert source.calls == ['integrated_operations', 'process']


def test_adapter_rejects_document_from_another_tool_even_if_source_returns_it() -> None:
    source = InMemoryDocumentSource({'process': _document(tool_key='integrated_operations')})

    with pytest.raises(TimeStatusToolScopeError, match="belongs to 'integrated_operations'"):
        TimeStatusStoreAdapter(source).load_snapshot(tool_key='process')

    assert source.calls == ['process']


def test_missing_document_stays_missing_without_fallback_to_other_tool() -> None:
    source = InMemoryDocumentSource({'integrated_operations': _document()})

    snapshot = TimeStatusStoreAdapter(source).load_snapshot(tool_key='process')

    assert snapshot is None
    assert source.calls == ['process']


def test_source_timestamps_are_normalized_to_utc() -> None:
    document = _document()
    document['sources'] = {
        'pi': datetime(2026, 8, 28, 18, 0, tzinfo=timezone(timedelta(hours=-4))),
        'dispatch': '2026-08-28T18:00:00-04:00',
    }

    snapshot = parse_time_status_store_document(
        document,
        expected_tool_key='integrated_operations',
    )

    assert snapshot.source('pi').timestamp_utc == datetime(2026, 8, 28, 22, 0, tzinfo=UTC)
    assert snapshot.source('dispatch').timestamp_iso == '2026-08-28T22:00:00Z'


def test_missing_and_invalid_source_timestamps_are_preserved_as_quality_states() -> None:
    document = _document()
    document['sources'] = {
        'pi': None,
        'dispatch': 'not-a-timestamp',
        'blockgrade': '2026-08-28T22:00:00',
    }

    snapshot = parse_time_status_store_document(
        document,
        expected_tool_key='integrated_operations',
    )

    assert snapshot.source('pi').quality is TimeStatusTimestampQuality.MISSING
    assert snapshot.source('pi').timestamp_utc is None
    assert snapshot.source('dispatch').quality is TimeStatusTimestampQuality.INVALID
    assert snapshot.source('blockgrade').quality is TimeStatusTimestampQuality.INVALID


def test_querying_absent_source_returns_missing_without_mutating_snapshot() -> None:
    snapshot = parse_time_status_store_document(
        _document(),
        expected_tool_key='integrated_operations',
    )
    before = tuple(snapshot.sources)

    missing = snapshot.source('fabrica')

    assert missing.quality is TimeStatusTimestampQuality.MISSING
    assert missing.key == 'fabrica'
    assert tuple(snapshot.sources) == before


@pytest.mark.parametrize(
    'patch, message',
    [
        ({'tool_key': None}, 'requires tool_key'),
        ({'generated_at_utc': None}, 'generated_at_utc'),
        ({'generated_at_utc': '2026-08-28T22:00:00'}, 'generated_at_utc'),
        ({'sources': None}, 'requires sources mapping'),
    ],
)
def test_invalid_envelope_is_rejected_as_contract_error(
    patch: dict[str, object],
    message: str,
) -> None:
    document = _document()
    document.update(patch)

    with pytest.raises(TimeStatusStoreContractError, match=message):
        parse_time_status_store_document(
            document,
            expected_tool_key='integrated_operations',
        )


def test_invalid_source_key_rejects_document_without_sanitizing_identity() -> None:
    document = _document()
    document['sources'] = {'PI Main': '2026-08-28T22:00:00Z'}

    with pytest.raises(TimeStatusStoreContractError, match='source key'):
        parse_time_status_store_document(
            document,
            expected_tool_key='integrated_operations',
        )


def test_future_timestamp_remains_structurally_valid_for_later_freshness_policy() -> None:
    document = _document()
    document['sources'] = {'pi': '2099-01-01T00:00:00Z'}

    snapshot = parse_time_status_store_document(
        document,
        expected_tool_key='integrated_operations',
    )

    assert snapshot.source('pi').quality is TimeStatusTimestampQuality.VALID
    assert snapshot.source('pi').timestamp_iso == '2099-01-01T00:00:00Z'


def test_adapter_is_stateless_and_reflects_source_on_each_load() -> None:
    first = _document()
    source = InMemoryDocumentSource({'integrated_operations': first})
    adapter = TimeStatusStoreAdapter(source)

    snapshot_a = adapter.load_snapshot(tool_key='integrated_operations')
    source.documents['integrated_operations'] = {
        'tool_key': 'integrated_operations',
        'generated_at_utc': '2026-08-28T22:02:05Z',
        'sources': {'pi': '2026-08-28T22:02:00Z'},
    }
    snapshot_b = adapter.load_snapshot(tool_key='integrated_operations')

    assert snapshot_a is not None and snapshot_b is not None
    assert snapshot_a.generated_at_iso == '2026-08-28T22:00:05Z'
    assert snapshot_b.generated_at_iso == '2026-08-28T22:02:05Z'
    assert source.calls == ['integrated_operations', 'integrated_operations']
