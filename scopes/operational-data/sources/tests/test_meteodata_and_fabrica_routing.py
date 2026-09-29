from atlanticus.operational_data.core import DataSource
from atlanticus.operational_data.sources import DataSourceApplications


def test_independent_producer_application_routes() -> None:
    routes = DataSourceApplications(
        pi='pi-app',
        fabrica_planes='operational-data-fabrica-planes-local',
        fabrica_kpis='operational-data-fabrica-kpis-local',
        meteodata='operational-data-meteodata-local',
    )
    assert (
        routes.application_for(DataSource.FABRICA_PLANES) == 'operational-data-fabrica-planes-local'
    )
    assert routes.application_for(DataSource.FABRICA_KPIS) == 'operational-data-fabrica-kpis-local'
    assert routes.application_for(DataSource.METEODATA_DATA) == 'operational-data-meteodata-local'
    assert (
        routes.application_for(DataSource.METEODATA_PROJECTION)
        == 'operational-data-meteodata-local'
    )
