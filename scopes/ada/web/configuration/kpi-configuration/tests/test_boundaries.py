from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src' / 'ada' / 'configuration' / 'kpi_configuration'


def test_domain_has_no_physical_infrastructure_or_web_dependency() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in ROOT.rglob('*.py')).casefold()
    for forbidden in (
        'cosmos',
        'sharepoint',
        'dash',
        'flask',
        'service bus',
        'databricks',
    ):
        assert forbidden not in source


def test_domain_does_not_import_tool_or_definition_implementation() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in ROOT.rglob('*.py'))
    assert 'ada.configuration.tools' not in source
    assert 'ada.configuration.kpi_definition' not in source


def test_delivery_is_a_projection_contract_not_a_domain_dependency() -> None:
    source = (ROOT / 'projection.py').read_text(encoding='utf-8')
    assert "'ada_kpi_configuration_projection'" in source
    assert 'ada.kpis.delivery' not in source
