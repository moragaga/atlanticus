from pathlib import Path


def test_tool_kpi_destination_bridge_is_composition_only() -> None:
    source = (
        (
            Path(__file__).parents[1]
            / 'src'
            / 'ada'
            / 'web'
            / 'application'
            / 'configuration_manager'
            / 'tool_kpi_destinations.py'
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


def test_bridge_does_not_duplicate_tool_kpi_destination_rules() -> None:
    source = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'application'
        / 'configuration_manager'
        / 'tool_kpi_destinations.py'
    ).read_text(encoding='utf-8')

    assert '.kpi_destination_keys' in source
    assert 'subcomponents' not in source
    assert 'alarm_subcomponent_addresses' not in source
