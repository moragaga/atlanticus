from ada.web.kpis.configuration import KpiCatalog


def test_catalog_exposes_only_authoritative_kpi_identity() -> None:
    catalog = KpiCatalog(kpi_keys=('throughput', 'recovery'))

    assert catalog.kpi_keys == ('throughput', 'recovery')
    assert catalog.keys == frozenset({'throughput', 'recovery'})
