from datetime import UTC, datetime

from atlanticus.web.compositions.users_manager import (
    UsersManagerDraftValidationWorkflow,
    UsersManagerExactSourceReaderWorkflow,
)
from atlanticus.web.manager import (
    DraftValidationWorkflow,
    ExactSourceReaderWorkflow,
    build_workspace_revision,
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
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdminState,
    build_users_profiles_admin_revision,
    default_users_profiles_configuration,
)


def _snapshot(*, published: bool = True) -> SourceSnapshot:
    current = None
    token = None
    if published:
        current = SourceReleaseSummary(
            release_ref=SourceReleaseRef(
                release_id=SourceReleaseId('release-1'),
                published_at_utc=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
            ),
            content_hash=Digest('sha256', 'hash-release-1'),
        )
        token = ConcurrencyToken('etag-1')
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=current,
        concurrency_token=token,
    )


class Administration:
    def __init__(self, state: UsersProfilesAdminState) -> None:
        self.state = state

    def load_current(self) -> UsersProfilesAdminState:
        return self.state



def test_manager_workspace_revision_matches_users_domain_draft_revision() -> None:
    configuration = default_users_profiles_configuration()
    payload = configuration.to_document()

    assert build_workspace_revision(payload) == build_users_profiles_admin_revision(configuration)

def test_users_validator_implements_generic_validation_capability() -> None:
    workflow = UsersManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'Admin',
    )

    assert isinstance(workflow, DraftValidationWorkflow)


def test_users_validator_accepts_canonical_users_profiles_payload() -> None:
    workflow = UsersManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'Admin',
    )
    payload = default_users_profiles_configuration().to_document()

    result = workflow.validate_draft(payload)

    assert result.valid is True
    assert result.draft_revision == build_workspace_revision(payload)
    assert result.issues == ()
    assert tuple(item.label for item in result.summary) == (
        'Usuarios',
        'Usuarios activos',
        'Perfiles funcionales',
    )


def test_users_validator_reports_invalid_canonical_contract_without_legacy_catalog() -> None:
    workflow = UsersManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'Admin',
    )
    payload = {'users': [], 'profiles': []}

    result = workflow.validate_draft(payload)

    assert result.valid is False
    assert result.draft_revision == build_workspace_revision(payload)
    assert len(result.issues) == 1
    assert result.issues[0].code == 'users.configuration.invalid'


def test_users_reader_implements_generic_exact_source_reader_capability() -> None:
    state = UsersProfilesAdminState(
        configuration=default_users_profiles_configuration(),
        source_snapshot=_snapshot(),
    )
    workflow = UsersManagerExactSourceReaderWorkflow(
        administration=Administration(state),
    )

    assert isinstance(workflow, ExactSourceReaderWorkflow)


def test_users_reader_returns_payload_and_exact_snapshot_together() -> None:
    configuration = default_users_profiles_configuration()
    state = UsersProfilesAdminState(
        configuration=configuration,
        source_snapshot=_snapshot(),
    )
    workflow = UsersManagerExactSourceReaderWorkflow(
        administration=Administration(state),
    )

    result = workflow.load_current_source_exact()

    assert result.snapshot == state.source_snapshot
    assert result.payload == configuration.to_document()


def test_users_reader_returns_empty_payload_only_when_source_does_not_exist() -> None:
    state = UsersProfilesAdminState(
        configuration=None,
        source_snapshot=_snapshot(published=False),
    )
    workflow = UsersManagerExactSourceReaderWorkflow(
        administration=Administration(state),
    )

    result = workflow.load_current_source_exact()

    assert result.snapshot.current is None
    assert result.payload is None
