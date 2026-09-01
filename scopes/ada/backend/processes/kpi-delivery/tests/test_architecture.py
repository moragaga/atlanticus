from __future__ import annotations

from pathlib import Path


def test_process_boundary_has_no_web_historian_or_timeseries_runtime_imports() -> None:
    root = Path(__file__).resolve().parents[1] / 'src'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    assert 'ada.web' not in source
    assert 'ada.processes.kpis_delivery' not in source
    assert 'ada.processes.kpis_timeseries_delivery' not in source
    assert 'ada.processes.kpi_timeseries_delivery' not in source


def test_configuration_is_owned_by_composition_not_job_reader() -> None:
    root = Path(__file__).resolve().parents[1] / 'src/ada/processes/kpi_delivery'
    job = (root / 'job.py').read_text(encoding='utf-8')
    composition = (root / 'composition.py').read_text(encoding='utf-8')

    assert 'KpiDeliveryConfigurationRepository' not in job
    assert 'configuration_repository.read()' in composition
