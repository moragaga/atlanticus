from ada.web.configuration import ConfigurationPageRequest, SortDirection
from ada.web.kpis.configuration import KpiConfiguration, KpiConfigurationBinding
from ada.web.kpis.configuration.web import (
    KpiConfigurationDataMode,
    KpiConfigurationQuery,
    KpiConfigurationSortField,
    query_kpi_configuration,
)


def _configuration(count: int) -> KpiConfiguration:
    return KpiConfiguration(
        bindings=tuple(
            KpiConfigurationBinding(
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
    page = query_kpi_configuration(_configuration(24), KpiConfigurationQuery())

    assert len(page.items) == 10
    assert page.total_count == 24
    assert page.page_count == 3


def test_management_query_filters_and_paginates() -> None:
    page = query_kpi_configuration(
        _configuration(24),
        KpiConfigurationQuery(
            destination_keys=('plant',),
            data_mode=KpiConfigurationDataMode.LATEST,
            page=ConfigurationPageRequest(page_size=20),
        ),
    )

    assert all('plant' in item.destination_keys for item in page.items)
    assert all(item.latest_enabled and not item.series_enabled for item in page.items)


def test_management_query_sorts_kpi_descending() -> None:
    page = query_kpi_configuration(
        _configuration(12),
        KpiConfigurationQuery(
            sort_field=KpiConfigurationSortField.KPI_KEY,
            sort_direction=SortDirection.DESC,
        ),
    )

    assert page.items[0].kpi_key == 'kpi_11'
