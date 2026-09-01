from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/ada/processes/kpi_historian'


def test_process_does_not_depend_on_web_or_other_processes() -> None:
    forbidden = (
        'ada.web',
        'ada.processes.kpi_runtime',
        'ada.processes.kpi_delivery',
        'ada.processes.kpis_historian',
        'atlanticus.data_producers',
        'CosmosClient',
    )
    content = '\n'.join(path.read_text(encoding='utf-8') for path in SOURCE.glob('*.py'))

    for token in forbidden:
        assert token not in content


def test_history_contract_is_consumed_instead_of_redeclared() -> None:
    content = (SOURCE / 'history.py').read_text(encoding='utf-8')

    assert 'DatasetDefinition(' not in content
    assert 'pa.schema(' not in content
    assert "DatasetKey(namespace=('kpis',), name='history')" not in content
