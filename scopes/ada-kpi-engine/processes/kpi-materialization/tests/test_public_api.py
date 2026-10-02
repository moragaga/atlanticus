import ada.processes.kpi_materialization as materialization


def test_public_api_exposes_materialization_process():
    assert materialization.__version__ == '1.0.0'
    assert callable(materialization.run)
    assert callable(materialization.read_connection_registry)
    assert materialization.KpiMaterializationJob is not None
