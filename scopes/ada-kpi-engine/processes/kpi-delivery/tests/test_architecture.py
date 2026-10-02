from pathlib import Path


def test_latest_delivery_keeps_process_boundary():
    root = Path(__file__).resolve().parents[1] / 'src'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    assert 'ada.web' not in source
    assert 'ada.processes.kpi_materialization' not in source
    assert 'ada.processes.kpi_timeseries_delivery' not in source
