from pathlib import Path


def test_shared_connection_contract_has_no_process_dependency():
    root = Path(__file__).resolve().parents[1] / 'src'
    content = '\n'.join(path.read_text(encoding='utf-8') for path in root.rglob('*.py'))
    assert 'ada.processes' not in content
