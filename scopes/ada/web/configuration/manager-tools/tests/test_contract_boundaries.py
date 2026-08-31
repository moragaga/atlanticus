from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manager_tools_has_no_persistence_projection_or_date_automation() -> None:
    source = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (ROOT / 'src/ada/web/configuration/manager_tools').rglob('*.py')
    )

    forbidden = (
        'SharePoint',
        'Cosmos',
        'publish_draft',
        'project(',
        'datetime',
        'current_date',
        'MonthDayWindow',
    )
    for token in forbidden:
        assert token not in source
