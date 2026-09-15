from datetime import UTC, datetime

from atlanticus.web.manager.lifecycle import resolve_manager_lifecycle
from atlanticus.web.manager.source import SourceReadResult
from atlanticus.web.manager.workspace import ManagerWorkspace, verify_workspace_source
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot(release: str, token: str = 'token-1') -> SourceSnapshot:
    release_ref = SourceReleaseRef(
        SourceReleaseId(release),
        datetime(2026, 9, 15, 18, 0, tzinfo=UTC),
    )
    return SourceSnapshot(
        SourceKey('tools'),
        SourceReleaseSummary(release_ref, Digest('sha256', 'a' * 64)),
        ConcurrencyToken(token),
    )


def _workspace(base: SourceSnapshot, payload: dict[str, object] | None = None) -> ManagerWorkspace:
    return ManagerWorkspace.create(
        owner_subject_id='user-1',
        payload=payload or {'enabled': True},
        base=base,
    )


def test_dirty_editor_only_allows_saving_local_work() -> None:
    base = _snapshot('release-1')
    workspace = _workspace(base)
    source = SourceReadResult(base, {'enabled': True})

    state = resolve_manager_lifecycle(
        workspace=workspace,
        editor_revision='editor-change',
        source=source,
        validation_current=True,
        source_verification=verify_workspace_source(workspace, base),
    )

    assert state.can_save_draft is True
    assert state.can_validate is False
    assert state.can_verify_source is False
    assert state.can_publish is False
    assert state.can_discard_local is True


def test_saved_changed_workspace_advances_validate_verify_publish_in_order() -> None:
    base = _snapshot('release-1')
    workspace = _workspace(base, {'enabled': False})
    source = SourceReadResult(base, {'enabled': True})

    saved = resolve_manager_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source=source,
        validation_current=False,
        source_verification=None,
    )
    validated = resolve_manager_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source=source,
        validation_current=True,
        source_verification=None,
    )
    verified = resolve_manager_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source=source,
        validation_current=True,
        source_verification=verify_workspace_source(workspace, base),
    )

    assert saved.can_validate is True
    assert validated.can_verify_source is True
    assert verified.can_publish is True
    assert verified.source_conflict is False


def test_changed_source_release_blocks_publication() -> None:
    base = _snapshot('release-1')
    workspace = _workspace(base, {'enabled': False})
    current = _snapshot('release-2', 'token-2')
    source = SourceReadResult(current, {'enabled': True})
    verification = verify_workspace_source(workspace, current)

    state = resolve_manager_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source=source,
        validation_current=True,
        source_verification=verification,
    )

    assert state.source_conflict is True
    assert state.can_publish is False


def test_published_workspace_has_no_local_lifecycle_action() -> None:
    base = _snapshot('release-1')
    payload = {'enabled': True}
    workspace = _workspace(base, payload)
    source = SourceReadResult(base, payload)

    state = resolve_manager_lifecycle(
        workspace=workspace,
        editor_revision=workspace.revision,
        source=source,
        validation_current=True,
        source_verification=verify_workspace_source(workspace, base),
    )

    assert state.published is True
    assert state.can_save_draft is False
    assert state.can_validate is False
    assert state.can_verify_source is False
    assert state.can_publish is False
    assert state.can_discard_local is False
