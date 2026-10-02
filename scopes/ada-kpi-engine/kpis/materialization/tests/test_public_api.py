import ada.kpis.materialization as materialization


def test_public_api_exposes_materialization_contract():
    assert materialization.__version__ == '1.0.0'
    assert callable(materialization.materialize_registry)
    assert callable(materialization.materialization_root)
    assert materialization.LocalKpiRegistryStore is not None
