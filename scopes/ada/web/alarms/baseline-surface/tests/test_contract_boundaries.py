from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'ada' / 'web' / 'alarms' / 'baseline_surface'


def test_surface_contract_does_not_introduce_alarm_data_or_body_dependencies() -> None:
    text = '\n'.join(path.read_text() for path in SRC.rglob('*') if path.suffix in {'.py', '.css'})
    forbidden = (
        'collector',
        'modal',
        'card',
        'severity',
        'acknowledgement',
        'alarm_count',
        'store_id',
        'callback',
        'body',
        'Cosmos',
        'SharePoint',
    )
    for token in forbidden:
        assert token not in text


def test_surface_has_no_runtime_alarm_state_styles() -> None:
    css = (SRC / 'resources' / 'css' / '10-alarm-baseline-surface.css').read_text()
    for token in ('origin', 'impact', 'critical', 'warning', 'active-color'):
        assert token not in css
