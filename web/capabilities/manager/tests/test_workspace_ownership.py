from atlanticus.web.manager import ManagerDraft, ManagerPrincipal
from atlanticus.web.manager.web.callbacks import _has_local_work, _local_workspace_state


def _principal(subject_id: str) -> ManagerPrincipal:
    return ManagerPrincipal(subject_id=subject_id, display_name=subject_id)


def _draft(owner_subject_id: str) -> ManagerDraft:
    return ManagerDraft.create(
        owner_subject_id=owner_subject_id,
        payload={'value': 'published'},
        base_source_revision='source-revision',
    )


def test_clean_source_workspace_is_not_local_work() -> None:
    principal = _principal('principal-current')
    source_draft = _draft(principal.subject_id)
    draft = source_draft.with_base_source_revision(source_draft.revision)

    resolved_draft, editor_revision = _local_workspace_state(
        draft.to_document(),
        draft.revision,
        principal,
    )

    assert resolved_draft == draft
    assert editor_revision == draft.revision
    assert _has_local_work(draft.to_document(), draft.revision, principal) is False


def test_modified_workspace_remains_local_work() -> None:
    principal = _principal('principal-current')
    draft = _draft(principal.subject_id)

    assert _has_local_work(draft.to_document(), draft.revision, principal) is True


def test_foreign_browser_workspace_does_not_block_current_principal_hydration() -> None:
    principal = _principal('principal-current')
    foreign_draft = _draft('principal-other')

    resolved_draft, editor_revision = _local_workspace_state(
        foreign_draft.to_document(),
        'fallback-editor-revision',
        principal,
    )

    assert resolved_draft is None
    assert editor_revision is None
    assert (
        _has_local_work(
            foreign_draft.to_document(),
            'fallback-editor-revision',
            principal,
        )
        is False
    )


def test_unsaved_editor_without_browser_draft_is_still_local_work() -> None:
    principal = _principal('principal-current')

    resolved_draft, editor_revision = _local_workspace_state(
        None,
        'unsaved-editor-revision',
        principal,
    )

    assert resolved_draft is None
    assert editor_revision == 'unsaved-editor-revision'
    assert _has_local_work(None, 'unsaved-editor-revision', principal) is True


def test_invalid_browser_workspace_does_not_block_source_hydration() -> None:
    principal = _principal('principal-current')
    invalid_draft = {'schema_version': 1, 'owner_subject_id': principal.subject_id}

    resolved_draft, editor_revision = _local_workspace_state(
        invalid_draft,
        'fallback-editor-revision',
        principal,
    )

    assert resolved_draft is None
    assert editor_revision is None
    assert _has_local_work(invalid_draft, 'fallback-editor-revision', principal) is False
