import ada.kpis.core as core


def test_public_version() -> None:
    assert core.__version__ == '1.0.0'
