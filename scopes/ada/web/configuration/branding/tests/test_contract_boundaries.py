from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_branding_configuration_has_no_date_activation_or_tool_dependency() -> None:
    source = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (ROOT / 'src/ada/configuration/branding').glob('*.py')
    )

    assert 'datetime' not in source
    assert 'date(' not in source
    assert 'ToolConfiguration' not in source
    assert 'tool_key' not in source
