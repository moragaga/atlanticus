from ada.web.kpis.registry.configuration import KpiRegistry, KpiRegistryBinding
from ada.web.kpis.registry.configuration.web import (
    KpiRegistryDataMode,
    KpiRegistryQuery,
    KpiRegistrySortField,
    query_kpi_configuration,
)
from ada.web.kpis.registry.configuration.web.query import SortDirection
from atlanticus.web.pagination import PageRequest


def _configuration(count: int) -> KpiRegistry:
    return KpiRegistry(
        bindings=tuple(
            KpiRegistryBinding(
                kpi_key=f'kpi_{index:02d}',
                destination_keys=('plant',) if index % 2 == 0 else ('crusher',),
                latest_enabled=index % 3 != 0,
                series_enabled=index % 3 == 0,
                series_hours=12 if index % 3 == 0 else None,
            )
            for index in range(count)
        )
    )


def test_default_management_page_is_ten_rows() -> None:
    page = query_kpi_configuration(_configuration(24), KpiRegistryQuery())

    assert len(page.items) == 10
    assert page.total_count == 24
    assert page.page_count == 3


def test_management_query_filters_and_paginates() -> None:
    page = query_kpi_configuration(
        _configuration(24),
        KpiRegistryQuery(
            destination_keys=('plant',),
            data_mode=KpiRegistryDataMode.LATEST,
            page=PageRequest(page_size=20),
        ),
    )

    assert all('plant' in item.destination_keys for item in page.items)
    assert all(item.latest_enabled and not item.series_enabled for item in page.items)


def test_management_query_sorts_kpi_descending() -> None:
    page = query_kpi_configuration(
        _configuration(12),
        KpiRegistryQuery(
            sort_field=KpiRegistrySortField.KPI_KEY,
            sort_direction=SortDirection.DESC,
        ),
    )

    assert page.items[0].kpi_key == 'kpi_11'
