from datetime import UTC, datetime

import pytest

from atlanticus.web.manager import (
    DraftValidationResult,
    ExactSourcePublicationResult,
    ExactSourceReadResult,
    ManagerPrincipal,
    ManagerProjectionError,
    ProjectionAuditRecord,
    build_workspace_revision,
)
from atlanticus.web.manager.exact_workspace import ManagerExactWorkspaceController
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot(release_id: str, token: str) -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', f'hash-{release_id}'),
        ),
        concurrency_token=ConcurrencyToken(token),
    )


def _publication(snapshot: SourceSnapshot) -> ExactSourcePublicationResult:
    assert snapshot.current is not None
    release = SourceReleaseMetadata(
        schema_version=1,
        source_key=snapshot.source_key,
        release_ref=snapshot.current.release_ref,
        content_hash=snapshot.current.content_hash,
        resources=(),
    )
    return ExactSourcePublicationResult(
        source=PublishResult(release=release, snapshot=snapshot),
        audit=ProjectionAuditRecord(
            actor='Admin',
            occurred_at=snapshot.current.release_ref.published_at_utc,
        ),
    )


class _Coordinator:
    def __init__(self) -> None:
        self.source = ExactSourceReadResult(
            snapshot=_snapshot('release-1', 'etag-1'),
            payload={'value': 'source'},
        )
        self.published: list[tuple[dict[str, object], SourceSnapshot]] = []
        self.validated: list[dict[str, object]] = []

    def load_current_source_exact(self, module_key, principal):
        return self.source

    def get_exact_source_snapshot(self, module_key, principal):
        return self.source.snapshot

    def validate_draft(self, module_key, principal, payload):
        self.validated.append(dict(payload))
        return DraftValidationResult(
            draft_revision=build_workspace_revision(payload),
            valid=True,
            audit=ProjectionAuditRecord(
                actor='Admin',
                occurred_at=datetime(2026, 9, 15, 15, 1, tzinfo=UTC),
            ),
        )

    def publish_draft_exact(self, module_key, principal, payload, expected_source_snapshot):
        self.published.append((dict(payload), expected_source_snapshot))
        published_snapshot = _snapshot('release-2', 'etag-2')
        self.source = ExactSourceReadResult(
            snapshot=published_snapshot,
            payload=dict(payload),
        )
        return _publication(published_snapshot)


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal('user-1', 'User One', is_local=True)


def _document(*, payload: dict[str, object] | None = None) -> dict[str, object]:
    workspace = ManagerWorkspace.create(
        owner_subject_id='user-1',
        payload=payload or {'value': 'draft'},
        base=_snapshot('release-1', 'etag-1'),
        saved_at_utc=datetime(2026, 9, 15, 15, 2, tzinfo=UTC),
    )
    document = workspace.to_document()
    document['document_type'] = 'domain_workspace'
    document['domain_metadata'] = {'keep': True}
    return document


def _validation(document: dict[str, object]) -> dict[str, object]:
    workspace = ManagerWorkspace.from_document(document)
    return {'draft_revision': workspace.revision, 'valid': True}


def test_publish_preserves_domain_metadata_and_rebases_to_published_snapshot() -> None:
    coordinator = _Coordinator()
    controller = ManagerExactWorkspaceController(coordinator)
    document = _document()
    workspace = ManagerWorkspace.from_document(document)
    verification = controller.verify(
        module_key='users',
        principal=_principal(),
        workspace_document=document,
        validation_document=_validation(document),
        editor_revision=workspace.revision,
    )

    result, updated = controller.publish(
        module_key='users',
        principal=_principal(),
        workspace_document=document,
        validation_document=_validation(document),
        verification_document=verification.to_document(),
        editor_revision=workspace.revision,
    )

    rebased = ManagerWorkspace.from_document(updated)
    assert updated['document_type'] == 'domain_workspace'
    assert updated['domain_metadata'] == {'keep': True}
    assert rebased.payload == workspace.payload
    assert rebased.base == result.source.snapshot
    assert rebased.base_payload_revision == rebased.revision
    assert coordinator.published == [(workspace.payload, verification.source)]


def test_keep_draft_preserves_payload_and_domain_metadata_while_adopting_new_release() -> None:
    coordinator = _Coordinator()
    controller = ManagerExactWorkspaceController(coordinator)
    document = _document()
    workspace = ManagerWorkspace.from_document(document)
    conflict = ManagerSourceVerification(
        workspace_revision=workspace.revision,
        base=workspace.base,
        source=_snapshot('release-2', 'etag-2'),
        checked_at_utc=datetime(2026, 9, 15, 15, 3, tzinfo=UTC),
    )

    updated = controller.keep_draft(
        principal=_principal(),
        workspace_document=document,
        verification_document=conflict.to_document(),
    )

    rebased = ManagerWorkspace.from_document(updated)
    assert updated['document_type'] == 'domain_workspace'
    assert updated['domain_metadata'] == {'keep': True}
    assert rebased.payload == workspace.payload
    assert rebased.base == conflict.source
    assert rebased.base_payload_revision == rebased.revision
    assert coordinator.published == []


def test_replace_from_source_preserves_domain_metadata_and_uses_source_payload() -> None:
    coordinator = _Coordinator()
    controller = ManagerExactWorkspaceController(coordinator)
    document = _document(payload={'value': 'local'})

    updated = controller.replace_from_source(
        module_key='users',
        principal=_principal(),
        workspace_document=document,
    )

    assert updated is not None
    replaced = ManagerWorkspace.from_document(updated)
    assert updated['document_type'] == 'domain_workspace'
    assert updated['domain_metadata'] == {'keep': True}
    assert replaced.payload == {'value': 'source'}
    assert replaced.base == coordinator.source.snapshot
    assert replaced.base_payload_revision == replaced.revision


def test_replace_from_empty_source_returns_none_without_fabricating_domain_document() -> None:
    coordinator = _Coordinator()
    coordinator.source = ExactSourceReadResult(
        snapshot=SourceSnapshot(
            source_key=SourceKey('users'),
            current=None,
            concurrency_token=None,
        ),
        payload=None,
    )
    controller = ManagerExactWorkspaceController(coordinator)

    assert (
        controller.replace_from_source(
            module_key='users',
            principal=_principal(),
            workspace_document=_document(),
        )
        is None
    )


def test_workspace_owner_is_enforced() -> None:
    coordinator = _Coordinator()
    controller = ManagerExactWorkspaceController(coordinator)
    document = _document()

    with pytest.raises(ManagerProjectionError, match='belongs to another user'):
        controller.require_workspace(
            document,
            ManagerPrincipal('user-2', 'User Two', is_local=True),
        )


def test_validation_uses_workspace_revision_and_never_publishes() -> None:
    coordinator = _Coordinator()
    controller = ManagerExactWorkspaceController(coordinator)
    document = _document()
    workspace = ManagerWorkspace.from_document(document)

    result = controller.validate(
        module_key='users',
        principal=_principal(),
        workspace_document=document,
        editor_revision=workspace.revision,
    )

    assert result.draft_revision == workspace.revision
    assert coordinator.validated == [workspace.payload]
    assert coordinator.published == []
