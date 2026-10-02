from pathlib import Path


def test_latest_delivery_has_no_web_timeseries_or_materialization_process_dependency():
    root = Path(__file__).resolve().parents[1] / 'src'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    assert 'ada.web' not in source
    assert 'ada.processes.kpi_materialization' not in source
    assert 'ada.processes.kpi_timeseries_delivery' not in source


def test_latest_delivery_owns_parallel_publication_without_dispatch_terminology():
    root = Path(__file__).resolve().parents[1] / 'src/ada/processes/kpi_delivery'
    parallel = (root / 'parallel.py').read_text(encoding='utf-8')
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    assert 'ThreadPoolExecutor' in parallel
    assert 'dispatch' not in source.casefold()


def test_latest_delivery_no_longer_reads_registry_from_cosmos():
    root = Path(__file__).resolve().parents[1] / 'src/ada/processes/kpi_delivery'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    assert 'ada-kpi-registry-projection' not in source
    assert 'KPI_REGISTRY_CONTAINER_SPEC' not in source
