from ada.web.configuration import ConfigurationPageRequest
from ada.web.kpis.definition import (
    KpiDefinition,
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
)
from ada.web.kpis.definition.web import (
    KpiDefinitionEditorStatus,
    KpiDefinitionQuery,
    KpiDefinitionStatusFilter,
    build_kpi_definition_editor_items,
    query_kpi_definitions,
)


def authority(*keys: str) -> KpiDefinitionAuthorityCatalog:
    return KpiDefinitionAuthorityCatalog(
        kpi_configuration_revision='kpi-config-r1',
        kpi_keys=tuple(keys),
    )


def test_editor_items_combine_authority_coverage_and_orphans() -> None:
    configuration = KpiDefinitionConfiguration(
        (
            KpiDefinition(kpi_key='defined', fields={'detail': 'Definido'}),
            KpiDefinition(kpi_key='orphan', fields={'detail': 'Huérfano'}),
        )
    )

    items = build_kpi_definition_editor_items(
        configuration,
        authority('defined', 'pending'),
    )

    assert tuple((item.kpi_key, item.status) for item in items) == (
        ('defined', KpiDefinitionEditorStatus.DEFINED),
        ('pending', KpiDefinitionEditorStatus.PENDING),
        ('orphan', KpiDefinitionEditorStatus.ORPHAN),
    )


def test_query_scales_to_five_hundred_authoritative_kpis() -> None:
    keys = tuple(f'kpi_{index:04d}' for index in range(500))
    page = query_kpi_definitions(
        KpiDefinitionConfiguration(),
        authority(*keys),
        KpiDefinitionQuery(
            page=ConfigurationPageRequest(page_number=1, page_size=10)
        ),
    )

    assert page.total_count == 500
    assert page.page_count == 50
    assert len(page.items) == 10
    assert page.items[0].kpi_key == 'kpi_0000'
    assert page.items[-1].kpi_key == 'kpi_0009'


def test_query_search_status_and_pagination_order() -> None:
    keys = tuple(f'crusher_{index:02d}' for index in range(25))
    configuration = KpiDefinitionConfiguration(
        tuple(
            KpiDefinition(
                kpi_key=key,
                fields={'detail': f'Detail {key}'},
            )
            for key in keys[:12]
        )
    )
    query = KpiDefinitionQuery(
        search='crusher',
        status=KpiDefinitionStatusFilter.PENDING,
        page=ConfigurationPageRequest(page_number=2, page_size=10),
    )

    page = query_kpi_definitions(configuration, authority(*keys), query)

    assert page.total_count == 13
    assert page.page_count == 2
    assert tuple(item.kpi_key for item in page.items) == (
        'crusher_22',
        'crusher_23',
        'crusher_24',
    )


def test_query_without_authority_is_empty_dependency_state() -> None:
    configuration = KpiDefinitionConfiguration(
        (KpiDefinition(kpi_key='existing', fields={'detail': 'Texto'}),)
    )

    page = query_kpi_definitions(
        configuration,
        None,
        KpiDefinitionQuery(),
    )

    assert page.total_count == 0
    assert page.items == ()
