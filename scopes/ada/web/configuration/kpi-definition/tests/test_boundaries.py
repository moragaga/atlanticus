from pathlib import Path


def test_kpi_definition_lifecycle_remains_manager_and_adapter_agnostic() -> None:
    package = Path(__file__).parents[1] / 'src' / 'ada' / 'configuration' / 'kpi_definition'
    source = '\n'.join(
        (package / name).read_text(encoding='utf-8') for name in ('lifecycle.py', 'services.py')
    )

    assert 'atlanticus.web.manager' not in source
    assert 'SharePoint' not in source
    assert 'Cosmos' not in source
