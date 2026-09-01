from pathlib import Path


def test_process_does_not_import_other_processes():
    root = Path(__file__).parents[1] / 'src'
    text = '\n'.join(path.read_text() for path in root.rglob('*.py'))
    assert 'ada.processes.kpi_historian' not in text
    assert 'ada.processes.kpi_delivery' not in text
    assert 'ada.processes.kpi_runtime' not in text
