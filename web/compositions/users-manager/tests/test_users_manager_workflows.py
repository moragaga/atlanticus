from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlanticus.web.compositions.users_manager import (
    UsersManagerSourceWorkflow,
    create_users_manager_source_workflow,
)
from atlanticus.web.manager import (
    SourceHistoryWorkflow,
    SourcePublicationWorkflow,
    SourceReaderWorkflow,
)
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
    UsersProfilesAdminState,
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
            published_at_utc=datetime(2026, 9, 15, 20, len(self.requests), tzinfo=UTC),
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


class _ReadingAdministration:
    def __init__(
        self,
        *,
        state: UsersProfilesAdminState,
        history: HistoryPage,
        history_configuration,
    ) -> None:
        self.state = state
        self.history = history
        self.history_configuration = history_configuration
        self.history_limits: list[int] = []
        self.loaded_releases: list[SourceReleaseRef] = []

    def get_source_snapshot(self) -> SourceSnapshot:
        return self.state.source_snapshot

    def load_current(self) -> UsersProfilesAdminState:
        return self.state

    def query_history(self, *, page_size: int = 20, cursor=None) -> HistoryPage:
        self.history_limits.append(page_size)
        return self.history

    def load_history_release(self, release_ref: SourceReleaseRef):
        self.loaded_releases.append(release_ref)
        return self.history_configuration


def _release_ref(value: str = 'release-1') -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 15, 19, 0, tzinfo=UTC),
    )


def _published_snapshot() -> SourceSnapshot:
    release_ref = _release_ref()
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


def _publishing_workflow(
    current: SourceSnapshot,
    *,
    actor: str = ' subject-admin ',
) -> tuple[UsersManagerSourceWorkflow, _RecordingSourceStore]:
    store = _RecordingSourceStore(current)
    administration = UsersProfilesAdministrationService(
        source=UsersSourceService(source=store, source_key=current.source_key),
        pending=_PendingReader(),
    )
    return (
        create_users_manager_source_workflow(
            administration=administration,
            audit_actor_provider=lambda: actor,
        ),
        store,
    )


def test_source_workflow_satisfies_generic_manager_contracts() -> None:
    workflow, _ = _publishing_workflow(_published_snapshot())

    assert isinstance(workflow, SourceReaderWorkflow)
    assert isinstance(workflow, SourceHistoryWorkflow)
    assert isinstance(workflow, SourcePublicationWorkflow)


def test_load_current_source_preserves_snapshot_and_canonical_payload() -> None:
    configuration = default_users_profiles_configuration()
    snapshot = _published_snapshot()
    release_ref = snapshot.current.release_ref
    history = HistoryPage(
        items=(
            SourceReleaseSummary(
                release_ref=release_ref,
                content_hash=Digest('sha256', 'a' * 64),
            ),
        )
    )
    administration = _ReadingAdministration(
        state=UsersProfilesAdminState(
            configuration=configuration,
            source_snapshot=snapshot,
        ),
        history=history,
        history_configuration=configuration,
    )
    workflow = UsersManagerSourceWorkflow(
        administration=administration,
        audit_actor_provider=lambda: 'admin',
    )

    result = workflow.load_current_source()

    assert result.snapshot is snapshot
    assert result.payload == configuration.to_document()


def test_load_current_source_returns_none_payload_when_source_is_empty() -> None:
    snapshot = _empty_snapshot()
    administration = _ReadingAdministration(
        state=UsersProfilesAdminState(configuration=None, source_snapshot=snapshot),
        history=HistoryPage(items=()),
        history_configuration=default_users_profiles_configuration(),
    )
    workflow = UsersManagerSourceWorkflow(
        administration=administration,
        audit_actor_provider=lambda: 'admin',
    )

    result = workflow.load_current_source()

    assert result.snapshot is snapshot
    assert result.payload is None


def test_history_preserves_generic_history_contract() -> None:
    configuration = default_users_profiles_configuration()
    release_ref = _release_ref('release-history')
    page = HistoryPage(
        items=(
            SourceReleaseSummary(
                release_ref=release_ref,
                content_hash=Digest('sha256', 'historyhash'),
            ),
        )
    )
    administration = _ReadingAdministration(
        state=UsersProfilesAdminState(
            configuration=configuration,
            source_snapshot=_published_snapshot(),
        ),
        history=page,
        history_configuration=configuration,
    )
    workflow = UsersManagerSourceWorkflow(
        administration=administration,
        audit_actor_provider=lambda: 'admin',
    )

    history = workflow.list_history(limit=11)
    release = workflow.load_history_release(release_ref)

    assert history is page
    assert release.release_ref == release_ref
    assert release.payload == configuration.to_document()
    assert administration.history_limits == [11]
    assert administration.loaded_releases == [release_ref]


def test_publish_preserves_snapshot_precondition_and_returns_generic_result() -> None:
    expected = _published_snapshot()
    workflow, store = _publishing_workflow(expected)
    configuration = default_users_profiles_configuration()

    result = workflow.publish_draft(configuration.to_document(), expected)

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
    workflow, store = _publishing_workflow(expected)

    workflow.publish_draft(default_users_profiles_configuration().to_document(), expected)

    request = store.requests[0]
    assert request.expected_concurrency_token is None
    assert request.basis_release is None


def test_invalid_payload_is_rejected_before_source_publication() -> None:
    workflow, store = _publishing_workflow(_published_snapshot())

    with pytest.raises(
        UsersConfigurationValidationError,
        match='Users/profiles configuration contract is invalid',
    ):
        workflow.publish_draft({'users': []}, workflow.get_source_snapshot())

    assert store.requests == []


def test_stale_snapshot_is_rejected_without_reaching_source_publish() -> None:
    expected = _published_snapshot()
    workflow, store = _publishing_workflow(expected)
    store.current = SourceSnapshot(
        source_key=expected.source_key,
        current=expected.current,
        concurrency_token=ConcurrencyToken('token-newer'),
    )

    with pytest.raises(UsersConfigurationSourceError, match='changed before publication'):
        workflow.publish_draft(default_users_profiles_configuration().to_document(), expected)

    assert store.requests == []
