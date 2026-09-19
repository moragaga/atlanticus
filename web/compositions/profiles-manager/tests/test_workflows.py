from datetime import UTC, datetime
from types import SimpleNamespace

from atlanticus.web.compositions.profiles_manager.workflows import (
    ProfilesManagerDraftValidationWorkflow,
    ProfilesManagerSourceWorkflow,
)
from atlanticus.web.manager.workspace import build_workspace_revision
from atlanticus.web.profiles.configuration.models import ProfilesConfiguration
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    HistoryPage,
    PublishResult,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _configuration(label: str = 'Analista') -> ProfilesConfiguration:
    return ProfilesConfiguration(
        profiles=(
            ProfileDefinition(
                key='11111111-1111-4111-8111-111111111111',
                label=label,
                background_color='#123456',
            ),
        )
    )


def _snapshot(*, token: str, release_id: str = 'release-1') -> SourceSnapshot:
    published_at = datetime(2026, 9, 19, 12, tzinfo=UTC)
    return SourceSnapshot(
        source_key=SourceKey('profiles-configuration'),
        current=SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId(release_id),
                published_at_utc=published_at,
            ),
            content_hash=Digest('sha256', 'a' * 64),
        ),
        concurrency_token=ConcurrencyToken(token),
    )


class _SourceService:
    def __init__(self, snapshots: list[SourceSnapshot]) -> None:
        self.source_key = SourceKey('profiles-configuration')
        self._snapshots = list(snapshots)
        self.published = None

    def get_current(self) -> SourceSnapshot:
        if len(self._snapshots) > 1:
            return self._snapshots.pop(0)
        return self._snapshots[0]

    def load_release(self, release_ref):
        return SimpleNamespace(release_ref=release_ref, configuration=_configuration())

    def query_history(self, *, page_size=20, cursor=None):
        return HistoryPage(items=(), next_cursor=None)

    def publish_configuration(
        self,
        configuration,
        *,
        published_by,
        expected_concurrency_token,
        basis_release,
    ):
        self.published = {
            'configuration': configuration,
            'published_by': published_by,
            'expected_concurrency_token': expected_concurrency_token,
            'basis_release': basis_release,
        }
        current = _snapshot(token='published', release_id='release-2')
        release = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.source_key,
            release_ref=current.current.release_ref,
            content_hash=current.current.content_hash,
            resources=(),
            previous_published_release=basis_release,
            basis_release=basis_release,
        )
        return PublishResult(release=release, snapshot=current)


def test_source_workflow_reads_current_payload_with_fresh_snapshot_token() -> None:
    original = _snapshot(token='token-1')
    refreshed = _snapshot(token='token-2')
    workflow = ProfilesManagerSourceWorkflow(
        source=_SourceService([original, refreshed]),
        audit_actor_provider=lambda: 'tester',
    )

    result = workflow.load_current_source()

    assert result.snapshot == refreshed
    assert result.payload == _configuration().to_document()


def test_source_workflow_publishes_with_fresh_token_when_release_identity_is_unchanged() -> None:
    expected = _snapshot(token='token-old')
    current = _snapshot(token='token-fresh')
    source = _SourceService([current])
    workflow = ProfilesManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'tester',
    )

    result = workflow.publish_draft(_configuration().to_document(), expected)

    assert source.published['expected_concurrency_token'] == current.concurrency_token
    assert source.published['basis_release'] == current.current.release_ref
    assert result.audit.actor == 'tester'
    assert result.summary


def test_validation_workflow_uses_manager_workspace_revision() -> None:
    payload = _configuration().to_document()
    workflow = ProfilesManagerDraftValidationWorkflow(audit_actor_provider=lambda: 'tester')

    result = workflow.validate_draft(payload)

    assert result.valid
    assert result.draft_revision == build_workspace_revision(payload)
    assert tuple(item.value for item in result.summary) == ('1', '5')


def test_validation_workflow_reports_invalid_profiles_payload() -> None:
    payload = {'profiles': 'invalid'}
    workflow = ProfilesManagerDraftValidationWorkflow(audit_actor_provider=lambda: 'tester')

    result = workflow.validate_draft(payload)

    assert not result.valid
    assert result.issues[0].code == 'profiles.configuration.invalid'
