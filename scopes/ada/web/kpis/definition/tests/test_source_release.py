from ada.web.kpis.definition import (
    KPI_DEFINITION_SOURCE_RESOURCE_PATH,
    KpiDefinitionSourceCodec,
    KpiDefinitionSourceService,
)
from atlanticus.web.source.models import SourceKey

from .helpers import SourceStoreStub, definition_configuration, release_ref


def test_definition_source_codec_round_trips_configuration() -> None:
    value = definition_configuration('throughput')
    codec = KpiDefinitionSourceCodec()

    resource = codec.encode(configuration=value, published_by='manager-user')
    decoded = codec.decode((resource,))

    assert resource.logical_path == KPI_DEFINITION_SOURCE_RESOURCE_PATH
    assert decoded.configuration == value
    assert decoded.published_by == 'manager-user'


def test_definition_source_codec_is_deterministic() -> None:
    codec = KpiDefinitionSourceCodec()
    value = definition_configuration('throughput')

    first = codec.encode(configuration=value, published_by='manager-user')
    second = codec.encode(configuration=value, published_by='manager-user')

    assert first.content == second.content


def test_definition_source_service_publishes_with_generic_concurrency_contract() -> None:
    source_key = SourceKey('ada-kpi-definition')
    current_ref = release_ref('current')
    store = SourceStoreStub(source_key=source_key, release_ref_value=current_ref)
    service = KpiDefinitionSourceService(source=store, source_key=source_key)

    service.publish_configuration(
        definition_configuration('throughput'),
        published_by='manager-user',
        expected_concurrency_token=store.snapshot.concurrency_token,
        basis_release=current_ref,
    )

    assert store.request is not None
    assert store.request.source_key == source_key
    assert store.request.expected_concurrency_token == store.snapshot.concurrency_token
    assert store.request.basis_release == current_ref
    assert len(store.request.resources) == 1


def test_definition_source_service_delegates_history_to_generic_store() -> None:
    source_key = SourceKey('ada-kpi-definition')
    store = SourceStoreStub(source_key=source_key, release_ref_value=release_ref('current'))
    service = KpiDefinitionSourceService(source=store, source_key=source_key)

    page = service.query_history(page_size=10, cursor=None)

    assert page.items == ()
