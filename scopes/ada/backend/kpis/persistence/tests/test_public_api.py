import ada.kpis.persistence as persistence


def test_public_version() -> None:
    assert persistence.__version__ == '1.0.0'
