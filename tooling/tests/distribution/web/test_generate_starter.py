from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_GENERATOR = Path(__file__).resolve().parents[3] / 'distribution/web/generate_starter.py'
_spec = importlib.util.spec_from_file_location('generate_web_starter', _GENERATOR)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
generate_starter = _module.generate_starter


@pytest.mark.parametrize('profile', ['generic', 'ada'])
def test_generated_starter_is_self_consistent_and_reproducible(tmp_path, profile, monkeypatch):
    if profile == 'ada':
        canonical = (
            tmp_path / 'scopes/ada/web/application/ada-generic-application/.env.detail'
        )
        canonical.parent.mkdir(parents=True)
        canonical.write_text('# Source contract fixture\n', encoding='utf-8')
        monkeypatch.setattr(_module, 'REPOSITORY_ROOT', tmp_path)
    first = generate_starter(profile=profile, destination=tmp_path / 'first')
    second = generate_starter(profile=profile, destination=tmp_path / 'second')
    manifest = json.loads((first / 'manifest.json').read_text(encoding='utf-8'))
    second_manifest = json.loads((second / 'manifest.json').read_text(encoding='utf-8'))

    assert manifest == second_manifest
    assert manifest['profile'] == profile
    assert manifest['qualification'] == 'UNVERIFIED'
    assert manifest['wheelhouse_included'] is False
    assert {
        relative: hashlib.sha256((first / relative).read_bytes()).hexdigest()
        for relative in manifest['files']
    } == manifest['files']
    if profile == 'ada':
        assert 'ada-generic-application' in (first / 'pyproject.toml').read_text()
        assert (first / '.env.detail').read_text() == '# Source contract fixture\n'
    else:
        assert 'ada-generic-application' not in (first / 'pyproject.toml').read_text()


def test_starter_generation_never_overwrites_an_existing_application(tmp_path):
    destination = tmp_path / 'application'
    generate_starter(profile='generic', destination=destination)
    with pytest.raises(FileExistsError):
        generate_starter(profile='ada', destination=destination)


def test_cli_generates_into_distribution_not_distributed(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(_module, 'REPOSITORY_ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['generate_starter.py', '--profile', 'generic'])
    _module.main()

    generated = tmp_path / 'distribution' / 'generic-web-starter'
    assert generated.is_dir()
    assert (generated / 'manifest.json').is_file()
    assert not (tmp_path / 'distributed').exists()
