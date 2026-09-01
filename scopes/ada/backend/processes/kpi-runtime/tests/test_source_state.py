from __future__ import annotations

from ada.processes.kpi_runtime.errors import KpiRuntimeSourceStateError
from ada.processes.kpi_runtime.source_state import PiOperationalWatermarkReader
from atlanticus.operational_data.sources import PiSourceProvider
from atlanticus.state import AtomicStateStore, StateKey
from tests.support import watermark


def test_pi_web_api_reads_durable_source_watermark(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='pi-source')
    store.replace(
        StateKey(namespace=('sources',), name='pi-web-api'),
        {
            'source': 'pi-web-api',
            'source_watermark_utc': '2026-08-31T20:10:00Z',
        },
    )

    result = PiOperationalWatermarkReader(
        store=store, provider=PiSourceProvider.PI_WEB_API
    ).current()

    assert result == watermark(10)


def test_notpii_uses_interpolated_stream_instead_of_manifest_max(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='notpii-source')
    store.replace(
        StateKey(namespace=('producers',), name='notpii'),
        {
            'producer': 'notpii',
            'revision': 3,
            'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
            'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
            'streams': {
                'interpolated': {
                    'revision': 2,
                    'source_watermark_utc': '2026-08-31T20:10:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:10:01.000000Z',
                },
                'recorded': {
                    'revision': 3,
                    'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
                },
            },
        },
    )

    result = PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII).current()

    assert result == watermark(10)


def test_notpii_interpolated_can_be_ahead_of_recorded(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='notpii-source')
    store.replace(
        StateKey(namespace=('producers',), name='notpii'),
        {
            'producer': 'notpii',
            'revision': 4,
            'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
            'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
            'streams': {
                'interpolated': {
                    'revision': 4,
                    'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
                },
                'recorded': {
                    'revision': 3,
                    'source_watermark_utc': '2026-08-31T20:10:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:10:01.000000Z',
                },
            },
        },
    )

    result = PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII).current()

    assert result == watermark(12)


def test_notpii_without_interpolated_stream_returns_none(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='notpii-source')
    store.replace(
        StateKey(namespace=('producers',), name='notpii'),
        {
            'producer': 'notpii',
            'revision': 1,
            'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
            'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
            'streams': {
                'recorded': {
                    'revision': 1,
                    'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
                }
            },
        },
    )

    result = PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII).current()

    assert result is None


def test_missing_source_state_returns_none(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='missing')

    assert (
        PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII).current()
        is None
    )


def test_notpii_state_without_streams_fails_closed(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='invalid')
    store.replace(
        StateKey(namespace=('producers',), name='notpii'),
        {'producer': 'notpii'},
    )

    try:
        PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII).current()
    except KpiRuntimeSourceStateError as error:
        assert 'streams must be a mapping' in str(error)
    else:
        raise AssertionError('invalid source state must fail closed')


def test_notpii_interpolated_stream_without_watermark_fails_closed(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='invalid-interpolated')
    store.replace(
        StateKey(namespace=('producers',), name='notpii'),
        {
            'producer': 'notpii',
            'streams': {
                'interpolated': {
                    'revision': 1,
                    'last_change_at_utc': '2026-08-31T20:10:01.000000Z',
                }
            },
        },
    )

    try:
        PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII).current()
    except KpiRuntimeSourceStateError as error:
        assert 'missing the source watermark contract' in str(error)
    else:
        raise AssertionError('invalid interpolated stream state must fail closed')
