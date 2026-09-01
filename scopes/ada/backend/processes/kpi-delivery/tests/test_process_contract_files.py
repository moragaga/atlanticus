from __future__ import annotations

import json
from pathlib import Path


def test_process_contract_files_are_present_and_non_secret() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / '.python-version').read_text(encoding='utf-8').strip() == '3.14.2'
    assert (root / '.env.detail').is_file()
    assert (root / 'config.detail.json').is_file()
    assert (root / 'secrets.detail.json').is_file()
    secrets = json.loads((root / 'secrets.detail.json').read_text(encoding='utf-8'))
    cosmos_key = next(item for item in secrets if item['var_name'] == 'COSMOS_CONSUMPTION_KEY')
    assert cosmos_key['value'] is None
    assert cosmos_key['exists_in_key_vault'] is True
