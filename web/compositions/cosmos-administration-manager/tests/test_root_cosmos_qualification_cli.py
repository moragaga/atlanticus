from __future__ import annotations

import sys

import pytest

from qualification.__main__ import main


def test_cli_requires_explicit_cosmos_credential(monkeypatch, capsys):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    monkeypatch.delenv('ATLANTICUS_COSMOS_QUALIFICATION_KEY', raising=False)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'qualification',
            '--connection-name',
            'local',
            '--endpoint',
            'http://127.0.0.1:8081',
            '--database',
            'test-db',
            '--allow-insecure-http',
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert 'ATLANTICUS_COSMOS_QUALIFICATION_KEY is required' in capsys.readouterr().err
