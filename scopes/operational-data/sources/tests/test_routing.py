import pytest

from atlanticus.operational_data.core import DataSource
from atlanticus.operational_data.sources import DataSourceApplications, DataSourceRoutingError


def test_application_routes_are_independent_by_operational_source() -> None:
    routes = DataSourceApplications(
        pi='pi-app', dispatch='dispatch-app', blockgrade='blockgrade-app',
        remanentes='remanentes-app', fabrica_planes='fabrica-planes-app',
        fabrica_kpis='fabrica-kpis-app',
    )
    assert routes.application_for(DataSource.PI_INTERPOLATED) == 'pi-app'
    assert routes.application_for(DataSource.PI_RECORDED) == 'pi-app'
    assert routes.application_for(DataSource.DISPATCH_STD_SHIFT_STATE) == 'dispatch-app'
    assert routes.application_for(DataSource.BLOCKGRADE_MMS_BLOCKGRADE_DETAILS_BUCKET) == 'blockgrade-app'
    assert routes.application_for(DataSource.REMANENTES_STOCKS) == 'remanentes-app'
    assert routes.application_for(DataSource.FABRICA_PLANES) == 'fabrica-planes-app'
    assert routes.application_for(DataSource.FABRICA_KPIS) == 'fabrica-kpis-app'


def test_missing_application_route_fails_only_when_source_is_requested() -> None:
    routes = DataSourceApplications(pi='pi-app', fabrica_planes='planes-only')
    routes.validate_sources((DataSource.PI_INTERPOLATED, DataSource.FABRICA_PLANES))
    with pytest.raises(DataSourceRoutingError, match='application route is not configured'):
        routes.validate_sources((DataSource.FABRICA_KPIS,))
