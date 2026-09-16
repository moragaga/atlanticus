import pytest

from ada.web.kpis.definition import (
    KpiDefinitionCoverageStatus,
    KpiDefinitionProjectionBuilder,
    KpiDefinitionProjectionError,
    KpiDefinitionSourceCodec,
    create_kpi_definition_projection_service,
)
from atlanticus.web.projection.errors import ProjectionExecutionError
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.models import Digest, SourceKey, SourceReleaseMetadata

from .helpers import (
    ProjectionStoreStub,
    SourceStoreStub,
    definition_configuration,
    kpi_configuration_projection,
    release_ref,
)


def test_service_selects_current_target_with_exact_kpi_configuration_dependency() -> None:
    source_key = SourceKey('ada-kpi-definition')
    source_ref = release_ref('definition-1')
    dependency = kpi_configuration_projection('throughput')
    source = SourceStoreStub(source_key=source_key, release_ref_value=source_ref)
    service = create_kpi_definition_projection_service(
        source=source,
        projection=ProjectionStoreStub(),
        kpi_configuration_projection=ProjectionStoreStub(dependency),
        kpi_configuration_source_key=dependency.source_key,
    )

    target = service.select_current_target(source_key)

    assert target is not None
    assert target.source_release == source_ref
    assert target.dependencies == (dependency.target,)


def test_definition_target_keeps_configuration_dependencies_transitive_not_flattened() -> None:
    source_key = SourceKey('ada-kpi-definition')
    source_ref = release_ref('definition-1')
    tool_target = ProjectionTarget(
        source_key=SourceKey('ada-tool-configuration'),
        source_release=release_ref('tool-1', hour=10),
    )
    dependency = kpi_configuration_projection(
        'throughput',
        dependencies=(tool_target,),
    )
    source = SourceStoreStub(source_key=source_key, release_ref_value=source_ref)
    service = create_kpi_definition_projection_service(
        source=source,
        projection=ProjectionStoreStub(),
        kpi_configuration_projection=ProjectionStoreStub(dependency),
        kpi_configuration_source_key=dependency.source_key,
    )

    target = service.select_current_target(source_key)

    assert target is not None
    assert target.dependencies == (dependency.target,)
    assert target.dependencies[0].dependencies == (tool_target,)
    assert tuple(item.source_key for item in target.dependencies) == (dependency.source_key,)


def test_projection_materializes_defined_and_missing_coverage() -> None:
    source_key = SourceKey('ada-kpi-definition')
    source_ref = release_ref('definition-1')
    dependency = kpi_configuration_projection('defined', 'missing')
    resource = KpiDefinitionSourceCodec().encode(
        configuration=definition_configuration('defined'),
        published_by='manager-user',
    )
    source = SourceStoreStub(
        source_key=source_key,
        release_ref_value=source_ref,
        resources=(resource,),
    )
    projection = ProjectionStoreStub()
    service = create_kpi_definition_projection_service(
        source=source,
        projection=projection,
        kpi_configuration_projection=ProjectionStoreStub(dependency),
        kpi_configuration_source_key=dependency.source_key,
    )
    target = service.select_current_target(source_key)
    assert target is not None

    result = service.project(target)

    assert result.projection.target == target
    assert result.projection.payload.configuration == definition_configuration('defined')
    assert tuple((item.kpi_key, item.status) for item in result.projection.payload.coverage) == (
        ('defined', KpiDefinitionCoverageStatus.DEFINED),
        ('missing', KpiDefinitionCoverageStatus.MISSING),
    )
    assert projection.calls == 1


def test_projection_rejects_orphan_definition() -> None:
    source_key = SourceKey('ada-kpi-definition')
    source_ref = release_ref('definition-1')
    dependency = kpi_configuration_projection('defined')
    target = ProjectionTarget(
        source_key=source_key,
        source_release=source_ref,
        dependencies=(dependency.target,),
    )
    release = SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=source_ref,
        content_hash=Digest('sha256', 'abc'),
        resources=(),
    )
    resources = (
        KpiDefinitionSourceCodec().encode(
            configuration=definition_configuration('defined', 'orphan'),
            published_by='manager-user',
        ),
    )

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='Published KPI Definition is not valid for projection',
    ):
        KpiDefinitionProjectionBuilder(
            kpi_configuration_projection=ProjectionStoreStub(dependency),
            kpi_configuration_source_key=dependency.source_key,
        ).build(target=target, release=release, resources=resources)


def test_projection_fails_if_kpi_configuration_changes_after_target_selection() -> None:
    source_key = SourceKey('ada-kpi-definition')
    source_ref = release_ref('definition-1')
    dependency_store = ProjectionStoreStub(kpi_configuration_projection('throughput', release='config-1'))
    resource = KpiDefinitionSourceCodec().encode(
        configuration=definition_configuration('throughput'),
        published_by='manager-user',
    )
    source = SourceStoreStub(
        source_key=source_key,
        release_ref_value=source_ref,
        resources=(resource,),
    )
    projection = ProjectionStoreStub()
    service = create_kpi_definition_projection_service(
        source=source,
        projection=projection,
        kpi_configuration_projection=dependency_store,
        kpi_configuration_source_key=dependency_store.value.source_key,
    )
    target = service.select_current_target(source_key)
    assert target is not None
    dependency_store.value = kpi_configuration_projection('throughput', release='config-2')

    with pytest.raises(ProjectionExecutionError) as error:
        service.project(target)

    assert isinstance(error.value.__cause__, KpiDefinitionProjectionError)
    assert str(error.value.__cause__) == (
        'KPI Configuration projection changed before KPI Definition projection'
    )
    assert projection.calls == 0


def test_target_selection_requires_kpi_configuration_projection() -> None:
    source_key = SourceKey('ada-kpi-definition')
    config_key = SourceKey('ada-kpi-configuration')
    source = SourceStoreStub(source_key=source_key, release_ref_value=release_ref('definition-1'))
    service = create_kpi_definition_projection_service(
        source=source,
        projection=ProjectionStoreStub(),
        kpi_configuration_projection=ProjectionStoreStub(),
        kpi_configuration_source_key=config_key,
    )

    with pytest.raises(
        KpiDefinitionProjectionError,
        match='KPI Configuration projection is not available',
    ):
        service.select_current_target(source_key)
