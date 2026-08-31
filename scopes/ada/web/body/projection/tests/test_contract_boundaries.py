from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'ada' / 'web' / 'body' / 'projection'


def test_projection_does_not_own_kpi_store_or_callback_contracts() -> None:
    text = '\n'.join(path.read_text() for path in SRC.glob('*.py'))

    assert 'kpi_latest_store_id' not in text
    assert 'kpi_timeseries_store_id' not in text
    assert 'callback' not in text.casefold()
    assert 'collector' not in text.casefold()


def test_projection_does_not_render_ui_or_alarm_state() -> None:
    text = '\n'.join(path.read_text() for path in SRC.glob('*.py'))

    assert 'from dash' not in text
    assert 'className' not in text
    assert 'severity' not in text.casefold()
    assert 'alarm_count' not in text.casefold()
