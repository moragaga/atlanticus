from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlanticus.web.compositions.users_manager import (
    UsersManagerExactSourceWorkflow,
    create_users_manager_exact_source_workflow,
)
from atlanticus.web.manager.exact_source import ExactSourcePublicationWorkflow
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    HistoryPage,
    HistoryQuery,
    IntegrityResult,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceResource,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration import (
    UsersProfilesAdministrationService,
    UsersSourceService,
    default_users_profiles_configuration,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationSourceError,
    UsersConfigurationValidationError,
)


class _PendingReader:
    def list_pending(self):
        return ()


class _RecordingSourceStore(SourceStore):
    def __init__(self, current: SourceSnapshot) -> None:
        self.current = current
        self.requests: list[PublishRequest] = []

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        assert source_key == self.current.source_key
        return self.current

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        raise NotImplementedError

    def publish(self, request: PublishRequest) -> PublishResult:
        self.requests.append(request)
        release_ref = SourceReleaseRef(
            release_id=SourceReleaseId(f'release-{len(self.requests) + 1}'),
            published_at_utc=datetime(2026, 9, 14, 20, len(self.requests), tzinfo=UTC),
        )
        content_hash = Digest('sha256', f'{len(self.requests):064x}')
        metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=request.source_key,
            release_ref=release_ref,
            content_hash=content_hash,
            resources=(),
            previous_published_release=(
                self.current.current.release_ref if self.current.current is not None else None
            ),
            basis_release=request.basis_release,
        )
        snapshot = SourceSnapshot(
            source_key=request.source_key,
            current=SourceReleaseSummary(release_ref=release_ref, content_hash=content_hash),
            concurrency_token=ConcurrencyToken(f'token-{len(self.requests) + 1}'),
        )
        self.current = snapshot
        return PublishResult(release=metadata, snapshot=snapshot)

    def query_history(self, query: HistoryQuery) -> HistoryPage:
        raise NotImplementedError

    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        raise NotImplementedError


def _published_snapshot() -> SourceSnapshot:
    release_ref = SourceReleaseRef(
        release_id=SourceReleaseId('release-1'),
        published_at_utc=datetime(2026, 9, 14, 19, 0, tzinfo=UTC),
    )
    return SourceSnapshot(
        source_key=SourceKey('users-profiles'),
        current=SourceReleaseSummary(
            release_ref=release_ref,
            content_hash=Digest('sha256', 'a' * 64),
        ),
        concurrency_token=ConcurrencyToken('token-1'),
    )


def _empty_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        source_key=SourceKey('users-profiles'),
        current=None,
        concurrency_token=None,
    )


def _workflow(
    current: SourceSnapshot,
    *,
    actor: str = ' subject-admin ',
) -> tuple[UsersManagerExactSourceWorkflow, _RecordingSourceStore]:
    store = _RecordingSourceStore(current)
    administration = UsersProfilesAdministrationService(
        source=UsersSourceService(source=store, source_key=current.source_key),
        pending=_PendingReader(),
    )
    return (
        create_users_manager_exact_source_workflow(
            administration=administration,
            audit_actor_provider=lambda: actor,
        ),
        store,
    )


def test_workflow_satisfies_manager_exact_source_protocol() -> None:
    workflow, _ = _workflow(_published_snapshot())

    assert isinstance(workflow, ExactSourcePublicationWorkflow)


def test_get_source_snapshot_preserves_exact_value_object() -> None:
    expected = _published_snapshot()
    workflow, _ = _workflow(expected)

    assert workflow.get_source_snapshot() is expected


def test_publish_exact_preserves_token_basis_release_and_source_result() -> None:
    expected = _published_snapshot()
    workflow, store = _workflow(expected)
    configuration = default_users_profiles_configuration()

    result = workflow.publish_draft_exact(configuration.to_document(), expected)

    request = store.requests[0]
    assert request.expected_concurrency_token == expected.concurrency_token
    assert request.basis_release == expected.current.release_ref
    assert result.source.release.basis_release == expected.current.release_ref
    assert result.source.snapshot == store.current
    assert result.audit.actor == 'subject-admin'
    assert result.audit.occurred_at == result.source.release.release_ref.published_at_utc
    assert result.summary == ()


def test_first_publish_preserves_empty_source_precondition() -> None:
    expected = _empty_snapshot()
    workflow, store = _workflow(expected)

    workflow.publish_draft_exact(default_users_profiles_configuration().to_document(), expected)

    request = store.requests[0]
    assert request.expected_concurrency_token is None
    assert request.basis_release is None


def test_invalid_payload_is_rejected_before_source_publication() -> None:
    workflow, store = _workflow(_published_snapshot())

    with pytest.raises(
        UsersConfigurationValidationError,
        match='Users/profiles configuration contract is invalid',
    ):
        workflow.publish_draft_exact({'users': []}, workflow.get_source_snapshot())

    assert store.requests == []


def test_stale_snapshot_is_rejected_without_reaching_source_publish() -> None:
    expected = _published_snapshot()
    workflow, store = _workflow(expected)
    store.current = SourceSnapshot(
        source_key=expected.source_key,
        current=expected.current,
        concurrency_token=ConcurrencyToken('token-newer'),
    )

    with pytest.raises(UsersConfigurationSourceError, match='changed before publication'):
        workflow.publish_draft_exact(default_users_profiles_configuration().to_document(), expected)

    assert store.requests == []
