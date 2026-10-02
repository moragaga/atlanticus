import ada.kpis.evaluation as evaluation


def test_public_version() -> None:
    assert evaluation.__version__ == '1.0.0'
