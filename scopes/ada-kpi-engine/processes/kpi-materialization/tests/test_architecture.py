from pathlib import Path


def test_process_does_not_depend_on_web_or_other_kpi_processes():
    root = Path(__file__).resolve().parents[1] / 'src'
    content = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    forbidden = (
        'ada.web',
        'ada.processes.kpi_runtime',
        'ada.processes.kpi_delivery',
        'ada.processes.kpi_historian',
        'ada.processes.kpi_timeseries_delivery',
    )
    assert all(token not in content for token in forbidden)
