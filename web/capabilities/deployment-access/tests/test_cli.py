from __future__ import annotations

import json
from types import SimpleNamespace

from atlanticus.web.deployment_access import cli, service as implementation
from atlanticus.web.deployment_access.material import DeploymentAccessIdentity


def test_bootstrap_cli_uses_external_destination_and_never_displays_password(
    tmp_path, monkeypatch, capsys
) -> None:
    project = tmp_path / 'project'
    project.mkdir()
    destination = tmp_path / 'secrets' / 'access.zip'
    destination.parent.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: 'Private-Secret-2026!')
    monkeypatch.setattr(
        implementation,
        'generate_material',
        lambda **_: (b'protected', DeploymentAccessIdentity('x' * 32, 'operator', 'example', 'qa')),
    )
    args = [
        'bootstrap',
        '--application',
        'example',
        '--environment',
        'qa',
        '--user',
        'operator',
        '--local-path',
        str(destination),
    ]
    assert cli.main(args) == 0
    assert destination.read_bytes() == b'protected'
    output = capsys.readouterr().out
    assert json.loads(output)['status'] == 'CREATED'
    assert 'Private-Secret' not in output
    assert cli.main(args) == 2
    assert destination.read_bytes() == b'protected'
