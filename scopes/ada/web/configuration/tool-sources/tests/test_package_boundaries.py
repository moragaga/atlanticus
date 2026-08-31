from pathlib import Path

import ada.configuration.tool_sources as tool_sources


def test_public_api_exposes_both_source_contract_dimensions() -> None:
    assert tool_sources.__all__ == [
        'SourceControlPolicy',
        'ToolSourceConsumption',
        'ToolSourceConsumptionValidationError',
        'ToolSourceOperationalParticipation',
        'ToolSourceOperationalParticipationValidationError',
        'validate_operational_participation_against_consumption',
    ]


def test_productive_package_does_not_reference_retired_module_names() -> None:
    package_root = Path(tool_sources.__file__).parent
    source = '\n'.join(path.read_text() for path in package_root.glob('*.py'))

    assert 'tool_source_consumption' not in source
    assert 'tool_source_operational_participation' not in source
