from datetime import datetime, timezone

import pytest

from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    HistoryQuery,
    IntegrityFailure,
    IntegrityResult,
    PublishRequest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceResource,
    SourceSnapshot,
)


def test_source_key_rejects_physical_paths() -> None:
    with pytest.raises(ValueError):
        SourceKey('configuration/tool')


def test_resource_path_accepts_logical_hierarchy_but_rejects_parent_escape() -> None:
    resource = SourceResource('tools/definition.json', b'{}')
    assert resource.logical_path == 'tools/definition.json'

    with pytest.raises(ValueError):
        SourceResource('../definition.json', b'{}')


def test_publish_request_rejects_duplicate_resource_paths() -> None:
    resource = SourceResource('definition.json', b'{}')
    with pytest.raises(ValueError):
        PublishRequest(
            source_key=SourceKey('tool-configuration'),
            resources=(resource, resource),
            expected_concurrency_token=None,
        )


def test_snapshot_requires_token_when_current_release_exists() -> None:
    release_ref = SourceReleaseRef(
        release_id=SourceReleaseId('r1'),
        published_at_utc=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError):
        SourceSnapshot(
            source_key=SourceKey('tool-configuration'),
            current=None,
            concurrency_token=ConcurrencyToken('token'),
        )

    empty = SourceSnapshot(SourceKey('tool-configuration'), None, None)
    assert empty.current is None
    assert release_ref.release_id.value == 'r1'


def test_history_query_normalizes_utc_bounds() -> None:
    query = HistoryQuery(
        source_key=SourceKey('tool-configuration'),
        published_from_utc=datetime(2026, 9, 12, tzinfo=timezone.utc),
        page_size=10,
    )
    assert query.published_from_utc is not None
    assert query.published_from_utc.tzinfo == timezone.utc


def test_integrity_result_derives_validity_from_failures() -> None:
    release_ref = SourceReleaseRef(
        release_id=SourceReleaseId('r1'),
        published_at_utc=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    valid = IntegrityResult(release_ref=release_ref, checked_resources=1)
    invalid = IntegrityResult(
        release_ref=release_ref,
        checked_resources=1,
        failures=(IntegrityFailure('digest_mismatch', 'Digest mismatch', 'definition.json'),),
    )
    assert valid.valid is True
    assert invalid.valid is False
    assert Digest('SHA256', 'ABC').algorithm == 'sha256'
