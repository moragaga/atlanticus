from pathlib import Path


def test_definition_web_uses_authority_contract_without_importing_kpi_configuration() -> None:
    package = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'kpis'
        / 'definition'
        / 'web'
    )
    source = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in package.rglob('*.py')
    )

    assert 'ada.web.kpis.configuration' not in source
    assert 'atlanticus.web.manager' not in source
    assert 'cosmos' not in source.lower()
    assert 'sharepoint' not in source.lower()
