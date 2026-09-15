from datetime import UTC, datetime

from atlanticus.web.compositions.users_manager import (
    UsersManagerExactSourceHistoryWorkflow,
    create_users_manager_exact_source_history_workflow,
)
from atlanticus.web.manager import ExactSourceHistoryWorkflow
from atlanticus.web.source.models import (
    Digest,
    HistoryPage,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
)
from atlanticus.web.users.configuration.admin_composition import (
    default_users_profiles_configuration,
)


def _release() -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId('release-history'),
        published_at_utc=datetime(2026, 9, 15, 20, 0, tzinfo=UTC),
    )


class _Administration:
    def __init__(self) -> None:
        self.release_ref = _release()
        self.page = HistoryPage(
            items=(
                SourceReleaseSummary(
                    release_ref=self.release_ref,
                    content_hash=Digest('sha256', 'historyhash'),
                ),
            )
        )
        self.limits: list[int] = []
        self.loaded: list[SourceReleaseRef] = []

    def query_history(self, *, page_size: int = 20, cursor=None) -> HistoryPage:
        self.limits.append(page_size)
        return self.page

    def load_history_release(self, release_ref: SourceReleaseRef):
        self.loaded.append(release_ref)
        return default_users_profiles_configuration()


def test_users_history_composition_preserves_exact_source_contracts() -> None:
    administration = _Administration()
    workflow = create_users_manager_exact_source_history_workflow(
        administration=administration,
    )

    assert isinstance(workflow, UsersManagerExactSourceHistoryWorkflow)
    assert isinstance(workflow, ExactSourceHistoryWorkflow)

    page = workflow.list_history_exact(limit=11)
    result = workflow.load_history_release_exact(administration.release_ref)

    assert page is administration.page
    assert result.release_ref == administration.release_ref
    assert result.payload == default_users_profiles_configuration().to_document()
    assert administration.limits == [11]
    assert administration.loaded == [administration.release_ref]
