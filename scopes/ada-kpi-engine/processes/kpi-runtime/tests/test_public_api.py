import ada.processes.kpi_runtime as runtime


def test_public_api_and_version() -> None:
    assert runtime.__version__ == '1.0.0'
    assert runtime.KpiRuntimeJob is not None
    assert runtime.PiOperationalWatermarkReader is not None
    assert runtime.RoutedDatasetSourceReader is not None
