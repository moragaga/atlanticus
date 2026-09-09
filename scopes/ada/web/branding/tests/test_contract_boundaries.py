from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_branding_core_has_no_date_activation_tool_or_dash_dependency() -> None:
    source = '\n'.join(
        path.read_text(encoding='utf-8') for path in (ROOT / 'src/ada/web/branding').glob('*.py')
    )

    assert 'datetime' not in source
    assert 'date(' not in source
    assert 'ToolConfiguration' not in source
    assert 'tool_key' not in source
    assert 'from dash' not in source
    assert 'import dash' not in source
