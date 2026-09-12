from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from atlanticus.web.projection.errors import ProjectionExecutionError, ProjectionInvariantError
from atlanticus.web.projection.models import (
    ProjectionAlignment,
    ProjectionAttemptOutcome,
    ProjectionRecord,
    ProjectionTarget,
)
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceResource,
    SourceSnapshot,
)


@dataclass
class FakeSource:
    current: SourceReleaseRef | None
    releases: dict[SourceReleaseRef, tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]]
    get_current_calls: int = 0
    read_calls: list[SourceReleaseRef] | None = None

    def __post_init__(self) -> None:
        self.read_calls = []

    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        self.get_current_calls += 1
        if self.current is None:
            return SourceSnapshot(source_key=source_key, current=None, concurrency_token=None)
        return SourceSnapshot(
            source_key=source_key,
            current=SourceReleaseSummary(
                release_ref=self.current,
                content_hash=Digest('sha256', 'same-content'),
            ),
            concurrency_token=ConcurrencyToken('token'),
        )

    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        assert self.read_calls is not None
        self.read_calls.append(release_ref)
        return self.releases[release_ref]


class FakeProjectionStore:
    def __init__(self, active: ProjectionRecord[str] | None = None) -> None:
        self.active = active
        self.replace_calls = 0

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[str] | None:
        return self.active

    def replace_active(self, projection: ProjectionRecord[str]) -> ProjectionRecord[str]:
        self.replace_calls += 1
        self.active = projection
        return projection


class RecordingBuilder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[SourceReleaseRef] = []

    def build(
        self,
        *,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> str:
        self.calls.append(release.release_ref)
        if self.fail:
            raise RuntimeError('projection builder failed')
        return resources[0].content.decode('utf-8')


def _release_ref(value: str, hour: int) -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 12, hour, tzinfo=UTC),
    )


def _release(
    source_key: SourceKey, release_ref: SourceReleaseRef, content: str
) -> tuple[
    SourceReleaseMetadata,
    tuple[SourceResource, ...],
]:
    return (
        SourceReleaseMetadata(
            schema_version=1,
            source_key=source_key,
            release_ref=release_ref,
            content_hash=Digest('sha256', 'same-content'),
            resources=(),
        ),
        (SourceResource('configuration.json', content.encode('utf-8')),),
    )


def _record(
    source_key: SourceKey,
    release_ref: SourceReleaseRef,
    payload: str,
) -> ProjectionRecord[str]:
    return ProjectionRecord(
        source_key=source_key,
        source_release_id=release_ref.release_id,
        source_published_at_utc=release_ref.published_at_utc,
        projected_at_utc=datetime(2026, 9, 12, 18, tzinfo=UTC),
        payload=payload,
    )


def test_project_reads_only_the_exact_target_even_when_source_current_is_newer() -> None:
    source_key = SourceKey('navigation')
    release_2 = _release_ref('release-2', 12)
    release_3 = _release_ref('release-3', 13)
    source = FakeSource(
        current=release_3,
        releases={release_2: _release(source_key, release_2, 'r2')},
    )
    store = FakeProjectionStore()
    builder = RecordingBuilder()
    service = SourceProjectionService(
        source=source,
        projection=store,
        builder=builder,
        clock=lambda: datetime(2026, 9, 12, 14, tzinfo=UTC),
    )

    result = service.project(ProjectionTarget(source_key=source_key, source_release=release_2))

    assert result.outcome is ProjectionAttemptOutcome.SUCCESS
    assert result.projection.source_release_id == release_2.release_id
    assert result.projection.payload == 'r2'
    assert source.read_calls == [release_2]
    assert source.get_current_calls == 0


def test_retry_uses_the_same_release_after_source_advances() -> None:
    source_key = SourceKey('navigation')
    release_2 = _release_ref('release-2', 12)
    release_3 = _release_ref('release-3', 13)
    source = FakeSource(
        current=release_3,
        releases={release_2: _release(source_key, release_2, 'r2')},
    )
    store = FakeProjectionStore()
    builder = RecordingBuilder()
    service = SourceProjectionService(source=source, projection=store, builder=builder)
    target = ProjectionTarget(source_key=source_key, source_release=release_2)

    service.project(target)
    service.project(target)

    assert source.read_calls == [release_2, release_2]
    assert builder.calls == [release_2, release_2]
    assert source.get_current_calls == 0


def test_builder_failure_does_not_replace_active_projection_and_preserves_retry_target() -> None:
    source_key = SourceKey('navigation')
    release_1 = _release_ref('release-1', 11)
    release_2 = _release_ref('release-2', 12)
    active = _record(source_key, release_1, 'r1')
    source = FakeSource(
        current=release_2,
        releases={release_2: _release(source_key, release_2, 'r2')},
    )
    store = FakeProjectionStore(active=active)
    service = SourceProjectionService(
        source=source,
        projection=store,
        builder=RecordingBuilder(fail=True),
    )
    target = ProjectionTarget(source_key=source_key, source_release=release_2)

    with pytest.raises(ProjectionExecutionError) as captured:
        service.project(target)

    assert captured.value.outcome is ProjectionAttemptOutcome.FAILED
    assert captured.value.target == target
    assert store.active == active
    assert store.replace_calls == 0


def test_status_is_never_projected_when_no_active_projection_exists() -> None:
    source_key = SourceKey('navigation')
    release_1 = _release_ref('release-1', 11)
    service = SourceProjectionService(
        source=FakeSource(current=release_1, releases={}),
        projection=FakeProjectionStore(),
        builder=RecordingBuilder(),
    )

    status = service.get_status(source_key)

    assert status.alignment is ProjectionAlignment.NEVER_PROJECTED
    assert status.source_current_release == release_1
    assert status.projected_source_release is None


def test_status_is_current_only_when_source_release_id_matches() -> None:
    source_key = SourceKey('navigation')
    release_2 = _release_ref('release-2', 12)
    service = SourceProjectionService(
        source=FakeSource(current=release_2, releases={}),
        projection=FakeProjectionStore(active=_record(source_key, release_2, 'r2')),
        builder=RecordingBuilder(),
    )

    status = service.get_status(source_key)

    assert status.alignment is ProjectionAlignment.CURRENT


def test_status_is_outdated_for_different_release_even_when_content_hash_is_same() -> None:
    source_key = SourceKey('navigation')
    release_1 = _release_ref('release-1', 11)
    release_2 = _release_ref('release-2', 12)
    service = SourceProjectionService(
        source=FakeSource(current=release_2, releases={}),
        projection=FakeProjectionStore(active=_record(source_key, release_1, 'same-payload')),
        builder=RecordingBuilder(),
    )

    status = service.get_status(source_key)

    assert status.alignment is ProjectionAlignment.OUTDATED
    assert status.source_current_release == release_2
    assert status.projected_source_release == release_1


def test_select_current_target_observes_current_once_and_returns_resolvable_ref() -> None:
    source_key = SourceKey('navigation')
    release_2 = _release_ref('release-2', 12)
    source = FakeSource(current=release_2, releases={})
    service = SourceProjectionService(
        source=source,
        projection=FakeProjectionStore(),
        builder=RecordingBuilder(),
    )

    target = service.select_current_target(source_key)

    assert target == ProjectionTarget(source_key=source_key, source_release=release_2)
    assert source.get_current_calls == 1


def test_project_rejects_source_provider_returning_a_different_release() -> None:
    source_key = SourceKey('navigation')
    requested = _release_ref('release-2', 12)
    wrong = _release_ref('release-3', 13)
    source = FakeSource(current=wrong, releases={requested: _release(source_key, wrong, 'r3')})
    service = SourceProjectionService(
        source=source,
        projection=FakeProjectionStore(),
        builder=RecordingBuilder(),
    )

    with pytest.raises(
        ProjectionInvariantError,
        match='Source store returned a different source release',
    ):
        service.project(ProjectionTarget(source_key=source_key, source_release=requested))


def test_failed_projection_can_retry_the_same_target_without_republish() -> None:
    source_key = SourceKey('navigation')
    release_2 = _release_ref('release-2', 12)
    source = FakeSource(
        current=release_2,
        releases={release_2: _release(source_key, release_2, 'r2')},
    )
    store = FakeProjectionStore()
    builder = RecordingBuilder(fail=True)
    service = SourceProjectionService(source=source, projection=store, builder=builder)
    target = ProjectionTarget(source_key=source_key, source_release=release_2)

    with pytest.raises(ProjectionExecutionError):
        service.project(target)

    builder.fail = False
    result = service.project(target)

    assert result.projection.source_release == release_2
    assert source.read_calls == [release_2, release_2]
    assert source.get_current_calls == 0


def test_status_is_outdated_when_projection_exists_but_source_has_no_current_release() -> None:
    source_key = SourceKey('navigation')
    release_1 = _release_ref('release-1', 11)
    service = SourceProjectionService(
        source=FakeSource(current=None, releases={}),
        projection=FakeProjectionStore(active=_record(source_key, release_1, 'r1')),
        builder=RecordingBuilder(),
    )

    status = service.get_status(source_key)

    assert status.alignment is ProjectionAlignment.OUTDATED
    assert status.source_current_release is None
    assert status.projected_source_release == release_1
