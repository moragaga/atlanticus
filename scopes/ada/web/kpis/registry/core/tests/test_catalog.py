from ada.web.kpis.registry.catalog import KpiCatalog


def test_registry_catalog_exposes_authoritative_kpi_identity() -> None:
    catalog = KpiCatalog(kpi_keys=('throughput', 'recovery'))

    assert catalog.kpi_keys == ('throughput', 'recovery')
    assert catalog.keys == frozenset({'throughput', 'recovery'})
