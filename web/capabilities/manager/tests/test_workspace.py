from datetime import UTC, datetime

import pytest

from atlanticus.web.manager.workspace import (
    ManagerProjectionState,
    ManagerWorkspace,
    prepare_conflict_overwrite,
    prepare_publication,
    resolve_manager_projection_state,
    select_projection_target,
    verify_workspace_source,
)
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)

SOURCE_KEY = SourceKey('tools')


def _snapshot(
    release_id: str | None,
    *,
    token: str | None = None,
    content_hash: str = 'content-a',
    minute: int = 0,
) -> SourceSnapshot:
    if release_id is None:
        return SourceSnapshot(source_key=SOURCE_KEY, current=None, concurrency_token=None)
    return SourceSnapshot(
        source_key=SOURCE_KEY,
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 12, 12, minute, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', content_hash),
        ),
        concurrency_token=ConcurrencyToken(token or f'token-{release_id}'),
    )


def _workspace(base: SourceSnapshot) -> ManagerWorkspace:
    return ManagerWorkspace.create(
        owner_subject_id='user-1',
        payload={'tools': [{'key': 'one', 'enabled': True}]},
        base=base,
        saved_at_utc=datetime(2026, 9, 12, 13, 0, tzinfo=UTC),
    )


def test_workspace_document_round_trip_preserves_exact_base_snapshot() -> None:
    workspace = _workspace(_snapshot('release-1', token='etag-1'))

    restored = ManagerWorkspace.from_document(workspace.to_document())

    assert restored == workspace
    assert restored.base.current is not None
    assert restored.base.current.release_ref.release_id == SourceReleaseId('release-1')
    assert restored.base.concurrency_token == ConcurrencyToken('etag-1')


def test_workspace_document_preserves_empty_base_for_first_publication() -> None:
    workspace = _workspace(_snapshot(None))

    restored = ManagerWorkspace.from_document(workspace.to_document())

    assert restored.base.current is None
    assert restored.base.concurrency_token is None


def test_workspace_revision_is_local_content_identity_not_source_release_identity() -> None:
    first = _workspace(_snapshot('release-1'))
    second = _workspace(_snapshot('release-2', minute=1))

    assert first.revision == second.revision
    assert first.base.current != second.base.current


def test_same_content_republication_is_still_a_source_conflict() -> None:
    workspace = _workspace(_snapshot('release-1', content_hash='same'))
    current = _snapshot('release-2', content_hash='same', minute=1)

    verification = verify_workspace_source(workspace, current)

    assert verification.matches is False
    assert verification.publishable is False
    assert verification.conflict is True


def test_normal_publication_uses_original_basis_and_fresh_matching_token() -> None:
    workspace = _workspace(_snapshot('release-1', token='token-base'))
    refreshed = _snapshot('release-1', token='token-fresh')
    verification = verify_workspace_source(workspace, refreshed)

    context = prepare_publication(verification)

    assert context.basis_release == workspace.base.current.release_ref
    assert context.expected_concurrency_token == ConcurrencyToken('token-fresh')
    assert context.matches_payload(workspace.payload) is True


def test_normal_publication_rejects_stale_base() -> None:
    workspace = _workspace(_snapshot('release-1'))
    verification = verify_workspace_source(workspace, _snapshot('release-2', minute=1))

    with pytest.raises(ValueError, match='source changed'):
        prepare_publication(verification)


def test_conflict_overwrite_keeps_original_basis_but_uses_fresh_source_token() -> None:
    workspace = _workspace(_snapshot('release-1', token='token-1'))
    current = _snapshot('release-2', token='token-2', minute=1)
    verification = verify_workspace_source(workspace, current)

    context = prepare_conflict_overwrite(verification)

    assert context.basis_release == workspace.base.current.release_ref
    assert context.expected_concurrency_token == ConcurrencyToken('token-2')


def test_conflict_overwrite_requires_an_actual_conflict() -> None:
    workspace = _workspace(_snapshot('release-1'))
    verification = verify_workspace_source(workspace, _snapshot('release-1'))

    with pytest.raises(ValueError, match='requires a source conflict'):
        prepare_conflict_overwrite(verification)


def test_projection_target_keeps_exact_selected_source_release() -> None:
    source = _snapshot('release-1')

    target = select_projection_target(source)

    assert target.source_key == SOURCE_KEY
    assert target.source_release == source.current.release_ref


def test_projection_target_requires_a_published_source() -> None:
    with pytest.raises(ValueError, match='without a published source release'):
        select_projection_target(_snapshot(None))


@pytest.mark.parametrize(
    ('status', 'expected'),
    (
        (
            ProjectionStatus(
                alignment=ProjectionAlignment.NEVER_PROJECTED,
                source_current_release=None,
                projected_source_release=None,
            ),
            ManagerProjectionState.NO_SOURCE,
        ),
        (
            ProjectionStatus(
                alignment=ProjectionAlignment.NEVER_PROJECTED,
                source_current_release=_snapshot('release-1').current.release_ref,
                projected_source_release=None,
            ),
            ManagerProjectionState.NEVER_PROJECTED,
        ),
        (
            ProjectionStatus(
                alignment=ProjectionAlignment.CURRENT,
                source_current_release=_snapshot('release-1').current.release_ref,
                projected_source_release=_snapshot('release-1').current.release_ref,
            ),
            ManagerProjectionState.CURRENT,
        ),
        (
            ProjectionStatus(
                alignment=ProjectionAlignment.OUTDATED,
                source_current_release=_snapshot('release-2', minute=1).current.release_ref,
                projected_source_release=_snapshot('release-1').current.release_ref,
            ),
            ManagerProjectionState.OUTDATED,
        ),
    ),
)
def test_projection_presentation_preserves_canonical_alignment_distinctions(
    status: ProjectionStatus,
    expected: ManagerProjectionState,
) -> None:
    assert resolve_manager_projection_state(status) is expected
