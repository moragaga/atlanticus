from datetime import UTC, datetime

from atlanticus.web.manager.workspace import ManagerWorkspace, select_projection_target, verify_workspace_source
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot(release: str, token: str) -> SourceSnapshot:
    ref = SourceReleaseRef(SourceReleaseId(release), datetime(2026, 9, 15, 18, 0, tzinfo=UTC))
    return SourceSnapshot(SourceKey('tools'), SourceReleaseSummary(ref, Digest('sha256', 'a' * 64)), ConcurrencyToken(token))


def test_workspace_v2_persists_generic_source_snapshot() -> None:
    workspace = ManagerWorkspace.create(owner_subject_id='user-1', payload={'enabled': True}, base=_snapshot('release-1', 'token-1'))

    document = workspace.to_document()
    restored = ManagerWorkspace.from_document(document)

    assert document['schema_version'] == 2
    assert restored == workspace


def test_verification_matches_the_same_release_even_if_concurrency_token_changes() -> None:
    base = _snapshot('release-1', 'token-1')
    workspace = ManagerWorkspace.create(owner_subject_id='user-1', payload={'enabled': True}, base=base)
    current = _snapshot('release-1', 'token-2')

    verification = verify_workspace_source(workspace, current)

    assert verification.matches
    assert verification.publishable


def test_verification_detects_a_different_source_release() -> None:
    base = _snapshot('release-1', 'token-1')
    workspace = ManagerWorkspace.create(owner_subject_id='user-1', payload={'enabled': True}, base=base)
    changed = _snapshot('release-2', 'token-2')

    verification = verify_workspace_source(workspace, changed)

    assert verification.conflict
    assert not verification.publishable


def test_projection_target_is_selected_directly_from_source_snapshot() -> None:
    snapshot = _snapshot('release-1', 'token-1')

    target = select_projection_target(snapshot)

    assert target.source_key == SourceKey('tools')
    assert target.source_release_id == SourceReleaseId('release-1')
