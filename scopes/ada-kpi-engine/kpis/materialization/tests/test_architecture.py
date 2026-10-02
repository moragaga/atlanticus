from pathlib import Path


def test_materialization_contract_has_no_web_cosmos_or_process_dependency():
    root = Path(__file__).resolve().parents[1] / 'src'
    content = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))

    for token in ('ada.web', 'ada.processes', 'atlanticus.connectivity'):
        assert token not in content
