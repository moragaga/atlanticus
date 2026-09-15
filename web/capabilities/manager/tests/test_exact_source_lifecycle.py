from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    ManagerWorkspace,
    resolve_exact_source_lifecycle,
    verify_workspace_source,
)
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot(
    release_id: str | None,
    token: str | None,
    *,
    source_key: str = 'users',
) -> SourceSnapshot:
    current = None
    if release_id is not None:
        current = SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', f'hash-{release_id}'),
        )
    return SourceSnapshot(
        source_key=SourceKey(source_key),
        current=current,
        concurrency_token=ConcurrencyToken(token) if token is not None else None,
    )


def _workspace(*, base: SourceSnapshot | None = None) -> ManagerWorkspace:
    return ManagerWorkspace.create(
        owner_subject_id='user-1',
        payload={'value': 1},
        base=base or _snapshot('release-1', 'etag-1'),
        saved_at_utc=datetime(2026, 9, 15, 12, 5, tzinfo=UTC),
    )


def _changed_workspace(*, base: SourceSnapshot | None = None) -> ManagerWorkspace:
    return _workspace(base=base).with_payload(
        {'value': 2},
        saved_at_utc=datetime(2026, 9, 15, 12, 6, tzinfo=UTC),
    )


def test_dirty_exact_editor_only_allows_saving_workspace() -> None:
    workspace = _changed_workspace()
    source = _snapshot('release-1', 'etag-1')

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision='editor-new',
        source_snapshot=source,
        validation_current=True,
        source_verification=verify_workspace_source(workspace, source),
    )

    assert state.can_save_draft is True
    assert state.can_validate is False
    assert state.can_verify_source is False
    assert state.can_publish is False
    assert state.can_force_publish is False
    assert state.can_discard_local is True


def test_saved_exact_workspace_allows_validation() -> None:
    workspace = _changed_workspace()
    source = _snapshot('release-1', 'etag-1')

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=source,
        validation_current=False,
        source_verification=None,
    )

    assert state.published is False
    assert state.can_validate is True
    assert state.can_verify_source is False
    assert state.can_publish is False


def test_valid_exact_workspace_allows_source_verification() -> None:
    workspace = _changed_workspace()
    source = _snapshot('release-1', 'etag-1')

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=source,
        validation_current=True,
        source_verification=None,
    )

    assert state.can_validate is False
    assert state.can_verify_source is True
    assert state.can_publish is False


def test_matching_exact_verification_allows_publication_without_force_path() -> None:
    workspace = _changed_workspace()
    source = _snapshot('release-1', 'etag-2')
    verification = verify_workspace_source(workspace, source)

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=source,
        validation_current=True,
        source_verification=verification,
    )

    assert verification.publishable is True
    assert state.verification_current is True
    assert state.source_conflict is False
    assert state.can_publish is True
    assert state.can_force_publish is False


def test_exact_release_conflict_blocks_publication_and_never_enables_force() -> None:
    workspace = _changed_workspace()
    source = _snapshot('release-2', 'etag-2')
    verification = verify_workspace_source(workspace, source)

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=source,
        validation_current=True,
        source_verification=verification,
    )

    assert verification.conflict is True
    assert state.source_conflict is True
    assert state.can_publish is False
    assert state.can_force_publish is False


def test_clean_workspace_on_current_release_is_published_even_if_token_refreshed() -> None:
    workspace = _workspace(base=_snapshot('release-1', 'etag-1'))
    source = _snapshot('release-1', 'etag-2')

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=source,
        validation_current=False,
        source_verification=None,
    )

    assert state.published is True
    assert state.can_validate is False
    assert state.can_verify_source is False
    assert state.can_publish is False
    assert state.can_discard_local is False


def test_clean_first_workspace_without_published_source_can_be_validated() -> None:
    source = _snapshot(None, None)
    workspace = _workspace(base=source)

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=source,
        validation_current=False,
        source_verification=None,
    )

    assert state.published is False
    assert state.can_validate is True
    assert state.can_discard_local is True


def test_changed_snapshot_invalidates_previous_exact_verification() -> None:
    workspace = _changed_workspace()
    verified_source = _snapshot('release-1', 'etag-1')
    current_source = _snapshot('release-1', 'etag-2')
    verification = verify_workspace_source(workspace, verified_source)

    state = resolve_exact_source_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source_snapshot=current_source,
        validation_current=True,
        source_verification=verification,
    )

    assert verification.publishable is True
    assert state.verification_current is False
    assert state.can_verify_source is True
    assert state.can_publish is False


def test_exact_lifecycle_rejects_a_different_source_key() -> None:
    workspace = _changed_workspace()

    with pytest.raises(
        ValueError,
        match='source key does not match current source',
    ):
        resolve_exact_source_lifecycle(
            workspace=workspace,
            editor_revision=workspace.revision,
            source_snapshot=_snapshot('release-1', 'etag-1', source_key='tools'),
            validation_current=False,
            source_verification=None,
        )
