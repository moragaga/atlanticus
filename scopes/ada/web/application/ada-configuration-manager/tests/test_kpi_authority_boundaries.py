from pathlib import Path


def test_kpi_authority_bridge_is_composition_only() -> None:
    source = (
        (
            Path(__file__).parents[1]
            / 'src'
            / 'ada'
            / 'web'
            / 'application'
            / 'configuration_manager'
            / 'kpi_authority.py'
        )
        .read_text(encoding='utf-8')
        .casefold()
    )

    for forbidden in (
        'cosmos',
        'sharepoint',
        'azure',
        'service bus',
        'databricks',
        'dash',
        'flask',
    ):
        assert forbidden not in source
