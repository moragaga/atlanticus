from ada.processes.kpi_runtime.catalog import build_catalog


def test_default_catalog_is_explicitly_empty() -> None:
    catalog = build_catalog()

    assert len(catalog) == 0
