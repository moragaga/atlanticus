from datetime import UTC, datetime, timedelta, timezone

import pytest

from ada.kpis.history import (
    HISTORIAN_AUTHORITY_NAME,
    HISTORIAN_AUTHORITY_NAMESPACE,
    HISTORIAN_AUTHORITY_SCHEMA_VERSION,
    KpiHistorianAuthority,
    KpiHistoryContractError,
    historian_revision,
)


def test_historian_authority_identity_is_shared_and_stable() -> None:
    assert HISTORIAN_AUTHORITY_NAMESPACE == ('kpis', 'history')
    assert HISTORIAN_AUTHORITY_NAME == 'authority'
    assert HISTORIAN_AUTHORITY_SCHEMA_VERSION == 1


def test_historian_authority_normalizes_utc_and_round_trips() -> None:
    authority = KpiHistorianAuthority(
        watermark_utc=datetime(2026, 9, 1, 8, 30, tzinfo=timezone(timedelta(hours=-4)))
    )

    assert authority.watermark_utc == datetime(2026, 9, 1, 12, 30, tzinfo=UTC)
    assert authority.revision == historian_revision(watermark_utc=authority.watermark_utc)
    assert KpiHistorianAuthority.from_payload(authority.to_payload()) == authority


def test_historian_authority_payload_is_explicit() -> None:
    authority = KpiHistorianAuthority(watermark_utc=datetime(2026, 9, 1, 12, 30, tzinfo=UTC))

    assert authority.to_payload() == {
        'schema_version': 1,
        'watermark_utc': '2026-09-01T12:30:00Z',
        'revision': authority.revision,
    }


def test_historian_authority_rejects_invalid_revision() -> None:
    authority = KpiHistorianAuthority(watermark_utc=datetime(2026, 9, 1, 12, 30, tzinfo=UTC))
    payload = authority.to_payload()
    payload['revision'] = 'invalid'

    with pytest.raises(KpiHistoryContractError, match='revision is invalid'):
        KpiHistorianAuthority.from_payload(payload)


def test_historian_authority_rejects_unexpected_fields() -> None:
    authority = KpiHistorianAuthority(watermark_utc=datetime(2026, 9, 1, 12, 30, tzinfo=UTC))
    payload = authority.to_payload()
    payload['extra'] = True

    with pytest.raises(KpiHistoryContractError, match='unexpected or missing fields'):
        KpiHistorianAuthority.from_payload(payload)


def test_historian_authority_rejects_subsecond_watermark() -> None:
    with pytest.raises(KpiHistoryContractError, match='whole seconds'):
        KpiHistorianAuthority(watermark_utc=datetime(2026, 9, 1, 12, 30, 0, 1, tzinfo=UTC))
