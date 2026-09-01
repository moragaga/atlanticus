import ada.processes.kpi_historian as historian


def test_public_api_and_version() -> None:
    assert historian.__version__ == '1.0.0'
    assert historian.KpiHistorianJob.__name__ == 'KpiHistorianJob'
    assert historian.KpiHistorianMaterializer.__name__ == 'KpiHistorianMaterializer'
    assert historian.KpiHistorianAuthorityStore.__name__ == 'KpiHistorianAuthorityStore'
