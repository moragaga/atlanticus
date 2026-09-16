from datetime import UTC, datetime
from types import SimpleNamespace

from atlanticus.web.source.models import (
    Digest,
    HistoryPage,
    SourceKey,
    SourceReleaseId,
    SourceReleaseRef,
    SourceReleaseSummary,
)
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdministrationService,
    default_users_profiles_configuration,
)


def _release() -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId('release-history'),
        published_at_utc=datetime(2026, 9, 15, 20, 0, tzinfo=UTC),
    )


class _Source:
    source_key = SourceKey('users')

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
        self.queries: list[tuple[int, str | None]] = []
        self.loaded: list[SourceReleaseRef] = []

    def query_history(self, *, page_size: int = 20, cursor: str | None = None) -> HistoryPage:
        self.queries.append((page_size, cursor))
        return self.page

    def load_release(self, release_ref: SourceReleaseRef):
        self.loaded.append(release_ref)
        configuration = default_users_profiles_configuration()
        return SimpleNamespace(
            payload=SimpleNamespace(
                projection_payload=lambda: configuration,
            )
        )


def test_administration_exposes_source_history_without_private_store_access() -> None:
    source = _Source()
    administration = UsersProfilesAdministrationService(
        source=source,
        pending=SimpleNamespace(list_pending=lambda: ()),
    )

    page = administration.query_history(page_size=7, cursor='next')
    configuration = administration.load_history_release(source.release_ref)

    assert page is source.page
    assert configuration == default_users_profiles_configuration()
    assert source.queries == [(7, 'next')]
    assert source.loaded == [source.release_ref]
