import pytest

from ada.web.kpis.registry.configuration import (
    KpiRegistryProjectionError,
    KpiRegistryProjectionBuilder,
    KpiRegistrySourceCodec,
    create_kpi_registry_projection_service,
)
from atlanticus.web.projection.errors import ProjectionExecutionError
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionTarget
from atlanticus.web.source.models import Digest, SourceKey, SourceReleaseMetadata

from .helpers import (
    DestinationProvider,
    ProjectionStoreStub,
    SourceStoreStub,
    configuration,
    destination_snapshot,
    release_ref,
    tool_target,
)


def test_service_selects_current_target_with_exact_tool_projection_dependency() -> None:
    source_key = SourceKey('kpis')
    source_ref = release_ref('kpi-1')
    provider = DestinationProvider(destination_snapshot('tool-1'))
    source = SourceStoreStub(source_key=source_key, release_ref_value=source_ref)
    service = create_kpi_registry_projection_service(
        source=source,
        projection=ProjectionStoreStub(),
        destinations=provider,
    )

    target = service.select_current_target(source_key)

    assert target is not None
    assert target.source_release == source_ref
    assert target.dependencies == (provider.value.projection_target,)


def test_projection_persists_generic_dependency_and_configuration_payload() -> None:
    source_key = SourceKey('kpis')
    source_ref = release_ref('kpi-1')
    provider = DestinationProvider(destination_snapshot('tool-1'))
    resource = KpiRegistrySourceCodec().encode(registry=configuration(), published_by='manager-user')
    source = SourceStoreStub(
        source_key=source_key,
        release_ref_value=source_ref,
        resources=(resource,),
    )
    projection = ProjectionStoreStub()
    service = create_kpi_registry_projection_service(
        source=source,
        projection=projection,
        destinations=provider,
    )
    target = service.select_current_target(source_key)
    assert target is not None

    result = service.project(target)

    assert result.projection.payload == configuration()
    assert result.projection.dependencies == (provider.value.projection_target,)
    assert result.projection.target == target
    assert projection.calls == 1


def test_status_becomes_outdated_when_tool_projection_target_changes() -> None:
    source_key = SourceKey('kpis')
    source_ref = release_ref('kpi-1')
    provider = DestinationProvider(destination_snapshot('tool-1'))
    resource = KpiRegistrySourceCodec().encode(registry=configuration(), published_by='manager-user')
    source = SourceStoreStub(
        source_key=source_key,
        release_ref_value=source_ref,
        resources=(resource,),
    )
    projection = ProjectionStoreStub()
    service = create_kpi_registry_projection_service(
        source=source,
        projection=projection,
        destinations=provider,
    )
    target = service.select_current_target(source_key)
    assert target is not None
    service.project(target)

    provider.value = destination_snapshot('tool-2')
    status = service.get_status(source_key)

    assert status.alignment is ProjectionAlignment.OUTDATED
    assert status.projected_dependencies == (tool_target('tool-1'),)
    assert status.current_dependencies == (tool_target('tool-2'),)


def test_projection_fails_if_tool_target_changes_after_target_selection() -> None:
    source_key = SourceKey('kpis')
    source_ref = release_ref('kpi-1')
    provider = DestinationProvider(destination_snapshot('tool-1'))
    resource = KpiRegistrySourceCodec().encode(registry=configuration(), published_by='manager-user')
    source = SourceStoreStub(
        source_key=source_key,
        release_ref_value=source_ref,
        resources=(resource,),
    )
    projection = ProjectionStoreStub()
    service = create_kpi_registry_projection_service(
        source=source,
        projection=projection,
        destinations=provider,
    )
    target = service.select_current_target(source_key)
    assert target is not None
    provider.value = destination_snapshot('tool-2')

    with pytest.raises(ProjectionExecutionError) as error:
        service.project(target)

    assert error.value.target == target
    assert isinstance(error.value.__cause__, KpiRegistryProjectionError)
    assert str(error.value.__cause__) == 'Tool projection changed before KPI Registry projection'
    assert projection.calls == 0


def test_projection_builder_rejects_destination_missing_from_tool_catalog() -> None:
    source_key = SourceKey('kpis')
    source_ref = release_ref('kpi-1')
    tool = tool_target('tool-1')
    provider = DestinationProvider(destination_snapshot('tool-1'))
    target = ProjectionTarget(
        source_key=source_key,
        source_release=source_ref,
        dependencies=(tool,),
    )
    release = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=source_ref,
        content_hash=Digest('sha256', 'abc'),
        resources=(),
    )
    resources = (
        KpiRegistrySourceCodec().encode(
            registry=configuration('unknown'),
            published_by='manager-user',
        ),
    )

    with pytest.raises(
        KpiRegistryProjectionError,
        match='Published KPI Registry is not valid for projection',
    ):
        KpiRegistryProjectionBuilder(destinations=provider).build(
            target=target,
            release=release,
            resources=resources,
        )


def test_target_selection_requires_tool_projection() -> None:
    source_key = SourceKey('kpis')
    source = SourceStoreStub(source_key=source_key, release_ref_value=release_ref('kpi-1'))
    service = create_kpi_registry_projection_service(
        source=source,
        projection=ProjectionStoreStub(),
        destinations=DestinationProvider(None),
    )

    with pytest.raises(KpiRegistryProjectionError, match='Tool projection is not available'):
        service.select_current_target(source_key)
