from pathlib import Path


def test_workflow_adapters_remain_thin_and_infrastructure_free() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )
    source = '\n'.join(path.read_text(encoding='utf-8') for path in package.rglob('*.py'))

    for forbidden in (
        'SharePoint',
        'Cosmos',
        'Databricks',
        'ServiceBus',
        'publish_bundle',
        'save(',
        'validate_ada_operational_tool_configuration',
    ):
        assert forbidden not in source
