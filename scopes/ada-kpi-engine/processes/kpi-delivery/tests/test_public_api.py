import ada.processes.kpi_delivery as package


def test_public_api_and_version():
    assert package.__version__ == '1.0.0'
    assert package.KpiLatestDeliveryJob is not None
    assert package.KpiLatestDeliveryRuntimeJob is not None
    assert package.KpiDeliveryComposition is not None
    assert package.FrozenKpiDeliveryConfiguration is not None
    assert package.ParallelKpiLatestPublisher is not None
    assert callable(package.load_frozen_delivery_configurations)
