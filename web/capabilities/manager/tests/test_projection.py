from datetime import UTC, datetime

from atlanticus.web.manager import (
    ManagerDraft,
    ProjectionAuditRecord,
    ProjectionState,
    ProjectionStatus,
    SourceVerificationResult,
    build_draft_revision,
    resolve_projection_state,
)

_AUDIT = ProjectionAuditRecord('Admin', datetime(2026, 8, 18, 12, 0, tzinfo=UTC))


def test_projection_state_is_no_source_without_published_configuration() -> None:
    assert resolve_projection_state(ProjectionStatus()) is ProjectionState.NO_SOURCE


def test_projection_state_is_ready_when_source_is_not_active() -> None:
    status = ProjectionStatus(source_revision='source-b', source_audit=_AUDIT)

    assert resolve_projection_state(status) is ProjectionState.READY


def test_projection_state_is_synchronized_when_active_source_matches() -> None:
    status = ProjectionStatus(
        source_revision='source-a',
        source_audit=_AUDIT,
        active_revision='projection-a',
        active_source_revision='source-a',
        projection_audit=_AUDIT,
    )

    assert resolve_projection_state(status) is ProjectionState.SYNCHRONIZED


def test_manager_draft_roundtrips_browser_contract_and_base_revision() -> None:
    payload = {'tools': [{'key': 'flotacion'}]}
    draft = ManagerDraft.create(
        owner_subject_id='user-1',
        payload=payload,
        base_source_revision='source-a',
        saved_at=datetime(2026, 8, 18, 12, 10, tzinfo=UTC),
    )

    restored = ManagerDraft.from_document(draft.to_document())

    assert restored == draft
    assert restored.revision == build_draft_revision(payload)
    assert restored.base_source_revision == 'source-a'
    assert restored.with_base_source_revision('source-b').base_source_revision == 'source-b'


def test_source_verification_requires_consistent_revision_state() -> None:
    checked_at = datetime(2026, 8, 18, 12, 15, tzinfo=UTC)
    result = SourceVerificationResult(
        draft_revision='draft-a',
        base_source_revision='source-a',
        source_revision='source-a',
        source_audit=_AUDIT,
        checked_at=checked_at,
    )

    restored = SourceVerificationResult.from_document(result.to_document())

    assert result.matches is True
    assert result.publishable is True
    assert result.conflict is False
    assert result.checked_at == checked_at
    assert restored == result


def test_source_verification_accepts_empty_source_when_draft_started_without_source() -> None:
    result = SourceVerificationResult(
        draft_revision='draft-a',
        base_source_revision=None,
        source_revision=None,
        source_audit=None,
        checked_at=datetime(2026, 8, 18, 12, 15, tzinfo=UTC),
    )

    assert result.matches is True
    assert result.publishable is True
    assert result.conflict is False


def test_source_verification_allows_publication_when_previous_base_exists_but_source_is_absent() -> (
    None
):
    result = SourceVerificationResult(
        draft_revision='draft-a',
        base_source_revision='source-a',
        source_revision=None,
        source_audit=None,
        checked_at=datetime(2026, 8, 18, 12, 15, tzinfo=UTC),
    )

    assert result.matches is False
    assert result.publishable is True
    assert result.conflict is False


def test_source_verification_marks_existing_different_revision_as_conflict() -> None:
    result = SourceVerificationResult(
        draft_revision='draft-a',
        base_source_revision='source-a',
        source_revision='source-b',
        source_audit=_AUDIT,
        checked_at=datetime(2026, 8, 18, 12, 15, tzinfo=UTC),
    )

    assert result.matches is False
    assert result.publishable is False
    assert result.conflict is True
