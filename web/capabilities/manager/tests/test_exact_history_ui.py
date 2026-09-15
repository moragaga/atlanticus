from datetime import UTC, datetime

from atlanticus.web.manager import (
    ExactSourceReadResult,
    ManagerPrincipal,
    ManagerWorkspace,
)
from atlanticus.web.manager.exact_workspace import ManagerExactWorkspaceController
from atlanticus.web.manager.web.ids import exact_history_preview_open_id
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def _snapshot() -> SourceSnapshot:
    release = SourceReleaseRef(
        release_id=SourceReleaseId('release-current'),
        published_at_utc=datetime(2026, 9, 15, 20, 0, tzinfo=UTC),
    )
    return SourceSnapshot(
        source_key=SourceKey('users'),
        current=SourceReleaseSummary(
            release_ref=release,
            content_hash=Digest('sha256', 'currenthash'),
        ),
        concurrency_token=ConcurrencyToken('etag-current'),
    )


class _Coordinator:
    def __init__(self) -> None:
        self.source = ExactSourceReadResult(
            snapshot=_snapshot(),
            payload={'value': 'current'},
        )

    def load_current_source_exact(self, module_key, principal):
        assert module_key == 'users'
        assert principal.subject_id == 'local'
        return self.source


def test_exact_history_id_preserves_full_release_identity() -> None:
    identifier = exact_history_preview_open_id(
        'users',
        'release-history',
        '2026-09-15T19:00:00+00:00',
        '0-2026-09-15T19:00:00+00:00',
        current=False,
        active=False,
    )

    assert identifier['release_id'] == 'release-history'
    assert identifier['published_at_utc'] == '2026-09-15T19:00:00+00:00'
    assert 'revision' not in identifier


def test_historical_payload_becomes_local_work_on_current_source_base() -> None:
    controller = ManagerExactWorkspaceController(_Coordinator())
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)

    document = controller.create_with_payload_on_current_base(
        module_key='users',
        principal=principal,
        payload={'value': 'historical'},
    )
    workspace = ManagerWorkspace.from_document(document)

    assert workspace.base == _snapshot()
    assert workspace.payload == {'value': 'historical'}
    assert workspace.has_local_changes is True
