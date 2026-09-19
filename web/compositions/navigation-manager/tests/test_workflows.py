from datetime import UTC, datetime
from types import SimpleNamespace

from atlanticus.web.compositions.navigation_manager.workflows import (
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
)
from atlanticus.web.manager.workspace import build_workspace_revision
from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.source_projection import NavigationProjectionIssue
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


def _catalog() -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='home',
                label='Inicio',
                href='/',
                enabled=True,
            ),
        )
    )


def _snapshot(*, token: str, release_id: str = 'release-1') -> SourceSnapshot:
    published_at = datetime(2026, 9, 15, 12, tzinfo=UTC)
    return SourceSnapshot(
        source_key=SourceKey('navigation-configuration'),
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
        self.source_key = SourceKey('navigation-configuration')
        self._snapshots = list(snapshots)
        self.published = None

    def get_current(self) -> SourceSnapshot:
        if len(self._snapshots) > 1:
            return self._snapshots.pop(0)
        return self._snapshots[0]

    def load_release(self, release_ref):
        return SimpleNamespace(release_ref=release_ref, catalog=_catalog())

    def query_history(self, *, page_size=20, cursor=None):
        return HistoryPage(items=(), next_cursor=None)

    def publish_catalog(
        self,
        catalog,
        *,
        published_by,
        expected_concurrency_token,
        basis_release,
    ):
        self.published = {
            'catalog': catalog,
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
    workflow = NavigationManagerSourceWorkflow(
        source=_SourceService([original, refreshed]),
        audit_actor_provider=lambda: 'tester',
    )

    result = workflow.load_current_source()

    assert result.snapshot == refreshed
    assert result.payload == _catalog().to_document()


def test_source_workflow_publishes_with_fresh_token_when_release_identity_is_unchanged() -> None:
    expected = _snapshot(token='token-old')
    current = _snapshot(token='token-fresh')
    source = _SourceService([current])
    workflow = NavigationManagerSourceWorkflow(
        source=source,
        audit_actor_provider=lambda: 'tester',
    )

    result = workflow.publish_draft(_catalog().to_document(), expected)

    assert source.published['expected_concurrency_token'] == current.concurrency_token
    assert source.published['basis_release'] == current.current.release_ref
    assert result.audit.actor == 'tester'


def test_validation_workflow_uses_manager_workspace_revision() -> None:
    payload = _catalog().to_document()
    workflow = NavigationManagerDraftValidationWorkflow(audit_actor_provider=lambda: 'tester')

    result = workflow.validate_draft(payload)

    assert result.valid
    assert result.draft_revision == build_workspace_revision(payload)
    assert result.summary


def test_validation_workflow_reports_invalid_navigation_payload() -> None:
    payload = {'links': 'invalid', 'groups': []}
    workflow = NavigationManagerDraftValidationWorkflow(audit_actor_provider=lambda: 'tester')

    result = workflow.validate_draft(payload)

    assert not result.valid
    assert result.issues[0].code == 'navigation.configuration.invalid'


def test_validation_workflow_applies_configured_navigation_validators() -> None:
    workflow = NavigationManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'tester',
        validators=(
            lambda _catalog: (
                NavigationProjectionIssue(
                    code='navigation.profile.unknown',
                    message="Unknown navigation profile 'operator'",
                ),
            ),
        ),
    )

    result = workflow.validate_draft(_catalog().to_document())

    assert not result.valid
    assert result.issues[0].code == 'navigation.profile.unknown'


def test_validation_workflow_preserves_warning_without_rejecting_draft() -> None:
    workflow = NavigationManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'tester',
        validators=(
            lambda _catalog: (
                NavigationProjectionIssue(
                    code='navigation.warning',
                    message='Navigation warning',
                    level='warning',
                ),
            ),
        ),
    )

    result = workflow.validate_draft(_catalog().to_document())

    assert result.valid
    assert result.issues[0].level == 'warning'
    assert result.summary
