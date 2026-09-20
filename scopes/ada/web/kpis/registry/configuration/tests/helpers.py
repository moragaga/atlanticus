from datetime import UTC, datetime

from ada.web.kpis.registry.configuration import (
    KpiRegistry,
    KpiRegistryBinding,
    KpiDestination,
    KpiDestinationCatalog,
    KpiDestinationCatalogSnapshot,
)
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceSnapshot,
)


def release_ref(value: str, *, hour: int = 12) -> SourceReleaseRef:
    return SourceReleaseRef(
        release_id=SourceReleaseId(value),
        published_at_utc=datetime(2026, 9, 16, hour, 0, tzinfo=UTC),
    )


def configuration(destination: str = 'crusher') -> KpiRegistry:
    return KpiRegistry(
        (
            KpiRegistryBinding(
                kpi_key='throughput',
                destination_keys=(destination,),
                series_enabled=True,
                series_hours=4,
            ),
        )
    )


def catalog() -> KpiDestinationCatalog:
    return KpiDestinationCatalog(
        destinations=(
            KpiDestination('global_indicators', 'Global Indicators'),
            KpiDestination('time_status', 'Time Status'),
            KpiDestination('crusher', 'Chancado'),
        )
    )


def tool_target(value: str = 'tool-1') -> ProjectionTarget:
    return ProjectionTarget(
        source_key=SourceKey('ada-tool-configuration'),
        source_release=release_ref(value, hour=11),
    )


def destination_snapshot(value: str = 'tool-1') -> KpiDestinationCatalogSnapshot:
    return KpiDestinationCatalogSnapshot(
        projection_target=tool_target(value),
        catalog=catalog(),
    )


class DestinationProvider:
    def __init__(self, value: KpiDestinationCatalogSnapshot | None) -> None:
        self.value = value

    def load(self):
        return self.value


class SourceStoreStub:
    def __init__(self, *, source_key: SourceKey, release_ref_value: SourceReleaseRef, resources=()):
        self.source_key = source_key
        self.release_ref = release_ref_value
        self.resources = tuple(resources)
        self.request = None
        self.snapshot = SourceSnapshot(
            source_key=source_key,
            current=SourceReleaseSummary(
                release_ref=release_ref_value,
                content_hash=Digest('sha256', 'abc'),
            ),
            concurrency_token=ConcurrencyToken('etag-1'),
        )

    def get_current(self, requested_source_key):
        assert requested_source_key == self.source_key
        return self.snapshot

    def read_release(self, requested_source_key, requested_release_ref):
        assert requested_source_key == self.source_key
        assert requested_release_ref == self.release_ref
        return (
            SourceReleaseMetadata(
                schema_version=1,
                source_key=self.source_key,
                release_ref=self.release_ref,
                content_hash=Digest('sha256', 'abc'),
                resources=(),
            ),
            self.resources,
        )

    def publish(self, request):
        self.request = request
        published_ref = release_ref('published', hour=13)
        metadata = SourceReleaseMetadata(
            schema_version=1,
            source_key=self.source_key,
            release_ref=published_ref,
            content_hash=Digest('sha256', 'def'),
            resources=(),
            basis_release=request.basis_release,
        )
        snapshot = SourceSnapshot(
            source_key=self.source_key,
            current=SourceReleaseSummary(
                release_ref=published_ref,
                content_hash=metadata.content_hash,
            ),
            concurrency_token=ConcurrencyToken('etag-2'),
        )
        from atlanticus.web.source.models import PublishResult

        return PublishResult(release=metadata, snapshot=snapshot)

    def query_history(self, query):
        from atlanticus.web.source.models import HistoryPage

        assert query.source_key == self.source_key
        return HistoryPage(items=())

    def verify_release(self, requested_source_key, requested_release_ref):
        raise AssertionError((requested_source_key, requested_release_ref))


class ProjectionStoreStub:
    def __init__(self) -> None:
        self.value = None
        self.calls = 0

    def get_active(self, source_key):
        if self.value is not None:
            assert self.value.source_key == source_key
        return self.value

    def replace_active(self, projection):
        self.calls += 1
        self.value = projection
        return projection
