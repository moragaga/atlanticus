from ada.web.kpis.registry.configuration import (
    KPI_REGISTRY_SOURCE_RESOURCE_PATH,
    KpiRegistrySourceCodec,
    KpiRegistrySourceService,
)
from atlanticus.web.source.models import SourceKey

from .helpers import SourceStoreStub, configuration, release_ref


def test_kpi_source_codec_round_trips_configuration() -> None:
    value = configuration()
    codec = KpiRegistrySourceCodec()

    resource = codec.encode(registry=value, published_by='manager-user')
    decoded = codec.decode((resource,))

    assert resource.logical_path == KPI_REGISTRY_SOURCE_RESOURCE_PATH
    assert decoded.registry == value
    assert decoded.published_by == 'manager-user'


def test_kpi_source_service_publishes_with_generic_concurrency_contract() -> None:
    source_key = SourceKey('kpis')
    current_ref = release_ref('current')
    store = SourceStoreStub(source_key=source_key, release_ref_value=current_ref)
    service = KpiRegistrySourceService(source=store, source_key=source_key)

    service.publish_registry(
        configuration(),
        published_by='manager-user',
        expected_concurrency_token=store.snapshot.concurrency_token,
        basis_release=current_ref,
    )

    assert store.request is not None
    assert store.request.source_key == source_key
    assert store.request.expected_concurrency_token == store.snapshot.concurrency_token
    assert store.request.basis_release == current_ref
    assert len(store.request.resources) == 1


def test_kpi_source_service_delegates_history_to_generic_store() -> None:
    source_key = SourceKey('kpis')
    store = SourceStoreStub(source_key=source_key, release_ref_value=release_ref('current'))
    service = KpiRegistrySourceService(source=store, source_key=source_key)

    page = service.query_history(page_size=10, cursor=None)

    assert page.items == ()
