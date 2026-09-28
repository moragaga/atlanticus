from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_STARTER = Path(__file__).resolve().parents[4] / 'distribution/web/starter/ada'
_PROJECT = _STARTER / 'tooling/project.py'
_RESOURCES = _STARTER / 'src/application/local_resources.py'


def _load_source(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _compose_fixture(tmp_path):
    root = tmp_path / 'distribution'
    paths = root / 'deployment/compose'
    paths.mkdir(parents=True)
    for name in ('infra', 'web', 'full'):
        (paths / f'{name}.yaml').write_bytes(
            (_STARTER / f'deployment/compose/{name}.yaml').read_bytes()
        )
    return root


def test_compose_full_accepts_existing_local_env_without_requiring_azure_secrets(
    tmp_path, monkeypatch,
):
    project = _load_source(_PROJECT, 'compose_project_full_test')
    root = _compose_fixture(tmp_path)
    (root / '.env').write_text(
        'ADA_TOOL_NAMESPACE=operaciones_integradas\n'
        'ADA_MANAGER_PERSISTENCE_PROVIDER=local\n'
        'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING=<unset-in-local-mode>\n',
        encoding='utf-8',
    )
    for key in ('ADA_TOOL_NAMESPACE', 'ADA_COMPOSE_NETWORK'):
        monkeypatch.delenv(key, raising=False)
    commands = []
    networks = []
    monkeypatch.setattr(project, '_running_compose_project', lambda *_args: False)
    monkeypatch.setattr(project, '_docker_network', lambda *_args, **kwargs: networks.append(kwargs))
    monkeypatch.setattr(project, '_command', lambda command, **_kwargs: commands.append(command))

    project.compose(root, 'up', 'full')

    assert networks == [{'create': True}]
    assert commands[:2] == [
        ['docker', 'volume', 'create', 'ada-generic-cosmos'],
        ['docker', 'volume', 'create', 'ada-generic-azurite'],
    ]
    assert commands[2][-2:] == ['up', '--detach']
    assert commands[2][0:2] == ['docker', 'compose']


def test_compose_rejects_placeholder_and_conflicting_full_stack(tmp_path, monkeypatch):
    project = _load_source(_PROJECT, 'compose_project_full_conflict_test')
    root = _compose_fixture(tmp_path)
    monkeypatch.delenv('ADA_TOOL_NAMESPACE', raising=False)
    (root / '.env').write_text('ADA_TOOL_NAMESPACE=<tool-namespace>\n', encoding='utf-8')
    with pytest.raises(project.ProjectError, match='ADA_TOOL_NAMESPACE'):
        project.compose(root, 'up', 'full')
    (root / '.env').write_text('ADA_TOOL_NAMESPACE=operaciones_integradas\n')
    monkeypatch.setattr(project, '_running_compose_project', lambda *_args: True)
    with pytest.raises(project.ProjectError, match='incompatible'):
        project.compose(root, 'up', 'full')


def test_compose_web_requires_durable_provider_and_prepares_only_explicitly(
    tmp_path, monkeypatch,
):
    project = _load_source(_PROJECT, 'compose_project_web_test')
    root = _compose_fixture(tmp_path)
    monkeypatch.delenv('ADA_MANAGER_PERSISTENCE_PROVIDER', raising=False)
    monkeypatch.delenv('ADA_TOOL_SOURCE_PROVIDER', raising=False)
    monkeypatch.delenv('ADA_TOOL_PROJECTION_PROVIDER', raising=False)
    (root / '.env').write_text(
        'ADA_MANAGER_PERSISTENCE_PROVIDER=local\n'
        'ADA_TOOL_SOURCE_PROVIDER=local\n'
        'ADA_TOOL_PROJECTION_PROVIDER=local\n', encoding='utf-8'
    )
    with pytest.raises(project.ProjectError, match='durable'):
        project.compose(root, 'up', 'web')
    (root / '.env').write_text(
        'ADA_MANAGER_PERSISTENCE_PROVIDER=durable\n'
        'ADA_TOOL_SOURCE_PROVIDER=blob\n'
        'ADA_TOOL_PROJECTION_PROVIDER=cosmos\n'
        'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING=emulator-test-value\n', encoding='utf-8'
    )
    executed = []
    monkeypatch.setattr(project, '_docker_network', lambda *_args, **kwargs: executed.append(kwargs))
    monkeypatch.setattr(project, '_command', lambda command, **_kwargs: executed.append(command))
    project.compose(root, 'up', 'web')
    assert executed[0] == {'create': True}
    assert executed[1][-2:] == ['up', '--detach']
    project.compose(root, 'prepare', 'web')
    assert executed[2] == {'create': True}
    assert executed[3][-6:] == ['--profile', 'setup', 'run', '--rm', '--no-deps', 'resources']
    with pytest.raises(project.ProjectError, match='only for web'):
        project.compose(root, 'prepare', 'infra')


def test_compose_infra_retains_volumes_on_down_and_does_not_need_env(tmp_path, monkeypatch):
    project = _load_source(_PROJECT, 'compose_project_infra_test')
    root = _compose_fixture(tmp_path)
    monkeypatch.setattr(project, '_running_compose_project', lambda *_args: False)
    executed = []
    monkeypatch.setattr(project, '_docker_network', lambda *_args, **kwargs: executed.append(kwargs))
    monkeypatch.setattr(project, '_command', lambda command, **_kwargs: executed.append(command))
    project.compose(root, 'up', 'infra')
    project.compose(root, 'down', 'infra')
    assert executed[0] == {'create': True}
    assert executed[1:3] == [
        ['docker', 'volume', 'create', 'ada-generic-cosmos'],
        ['docker', 'volume', 'create', 'ada-generic-azurite'],
    ]
    assert executed[3][-2:] == ['up', '--detach']
    assert executed[4][-1] == 'down'
    assert '--volumes' not in executed[4]


def test_compose_network_creation_and_persistent_volume_preparation(tmp_path, monkeypatch):
    project = _load_source(_PROJECT, 'compose_project_network_test')
    root = tmp_path
    monkeypatch.delenv('ADA_COMPOSE_NETWORK', raising=False)
    monkeypatch.setattr(project.subprocess, 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=1))
    with pytest.raises(project.ProjectError, match='start infra or full'):
        project._docker_network(root, create=False)
    called = []
    monkeypatch.setattr(project, '_command', lambda command, **_kwargs: called.append(command))
    project._docker_network(root, create=True)
    assert called == [['docker', 'network', 'create', '--driver', 'bridge',
                       'ada-generic-support']]
    project._docker_volumes(root)
    assert called[1:] == [
        ['docker', 'volume', 'create', 'ada-generic-cosmos'],
        ['docker', 'volume', 'create', 'ada-generic-azurite'],
    ]


def _load_local_resources(monkeypatch, *, endpoint='http://cosmos-emulator:8081',
                          environment='local'):
    calls = []

    def module(name, **members):
        parts = name.split('.')
        for index in range(1, len(parts)):
            parent = '.'.join(parts[:index])
            if parent not in sys.modules:
                item = ModuleType(parent)
                item.__path__ = []
                monkeypatch.setitem(sys.modules, parent, item)
        obj = ModuleType(name)
        obj.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, obj)
        return obj

    class Secret:
        def get_secret_value(self):
            return 'DefaultEndpointsProtocol=http;BlobEndpoint=http://azurite:10000/devstoreaccount1;'

    class Settings:
        def __init__(self):
            self.environment = SimpleNamespace(is_local=environment == 'local')
            self.tool_source_provider = SimpleNamespace(value='blob')
            self.tool_projection_provider = SimpleNamespace(value='cosmos')
            self.tool_projection_cosmos_endpoint = endpoint
            self.tool_source_blob_connection_string = Secret()
            self.tool_source_blob_container_name = 'ada-source'

    @contextmanager
    def manager(settings):
        calls.append('manager-open')
        try:
            yield 'manager-deployment'
        finally:
            calls.append('manager-closed')

    def prepare(deployment, *, action, environment, observe_failure=None):
        calls.append(('ensure', deployment, action, environment))
        return SimpleNamespace(status='COMPLETED', results=())

    module('ada.web.application.generic.manager_deployment',
           open_durable_manager=manager, prepare_durable_manager_resources=prepare)
    module('ada.web.application.generic.settings', AdaGenericSettings=Settings)
    module('atlanticus.web.configuration', WebEnvironment=SimpleNamespace(LOCAL='local'))
    resources = _load_source(_RESOURCES, 'compose_local_resources_test')
    return resources, calls


def test_local_resource_job_creates_only_missing_emulator_resources(monkeypatch):
    resources, calls = _load_local_resources(monkeypatch)
    monkeypatch.setattr(resources, '_wait_for_emulators', lambda: calls.append('ready'))
    assert resources.prepare_local_resources().status == 'COMPLETED'
    assert calls == [
        'ready',
        'manager-open',
        ('ensure', 'manager-deployment', 'prepare', 'local'),
        'manager-closed',
    ]


@pytest.mark.parametrize('endpoint,environment', [
    ('https://real-cosmos.documents.azure.com:443', 'local'),
    ('http://cosmos-emulator:8081', 'production'),
])
def test_resource_job_refuses_real_endpoint_and_production(
    monkeypatch, endpoint, environment,
):
    resources, calls = _load_local_resources(
        monkeypatch, endpoint=endpoint, environment=environment,
    )
    monkeypatch.setattr(resources, '_wait_for_emulators',
                        lambda: pytest.fail('Non-local initialization attempted'))
    with pytest.raises(RuntimeError, match='isolated Compose emulators'):
        resources.prepare_local_resources()
    assert calls == []


def test_ada_compose_templates_ship_with_generator_and_unchanged_source_inventory(
    tmp_path, monkeypatch,
):
    generator = _load_source(_STARTER.parents[1] / 'generate_starter.py',
                             'compose_generated_starter_test')
    env = tmp_path / 'repo/scopes/ada/web/application/ada-generic-application/.env.detail'
    env.parent.mkdir(parents=True)
    env.write_text('# @distribution manual-default\nADA_TOOL_SOURCE_PROVIDER=blob\n')
    monkeypatch.setattr(generator, 'REPOSITORY_ROOT', tmp_path / 'repo')
    target = generator.generate_starter(profile='ada', destination=tmp_path / 'ada-starter')
    inventory = json.loads((target / 'manifest.json').read_text())['files']
    for name in ('full.yaml', 'infra.yaml', 'web.yaml'):
        relative = f'deployment/compose/{name}'
        assert relative in inventory
        assert (target / relative).read_bytes() == (
            _STARTER / relative
        ).read_bytes()
    assert (target / 'src/application/local_resources.py').is_file()
    assert not (target / '.env').exists()


def test_source_and_compose_pedagogical_mirrors_are_equivalent():
    for primary, commented in (
        ('tooling/project.py', 'commented/tooling/project.py'),
        ('src/application/local_resources.py', 'commented/application/local_resources.py'),
    ):
        assert ast.dump(ast.parse((_STARTER / primary).read_text()), include_attributes=False) == (
            ast.dump(ast.parse((_STARTER / commented).read_text()), include_attributes=False)
        )
    for profile in ('infra', 'web', 'full'):
        mirror = (
            _STARTER / f'commented/deployment/compose/{profile}.yaml'
        ).read_text().splitlines(keepends=True)
        assert ''.join(line for line in mirror if not line.lstrip().startswith('#')) == (
            _STARTER / f'deployment/compose/{profile}.yaml'
        ).read_text()


@pytest.mark.skipif(shutil.which('docker') is None, reason='Docker Compose CLI not installed')
@pytest.mark.parametrize('profile', ('infra', 'web', 'full'))
def test_docker_compose_accepts_generated_service_graph(tmp_path, profile):
    root = _compose_fixture(tmp_path)
    (root / '.env').write_text(
        'ADA_TOOL_NAMESPACE=operaciones_integradas\n'
        'ADA_MANAGER_PERSISTENCE_PROVIDER=durable\n'
        'ADA_TOOL_SOURCE_PROVIDER=blob\n'
        'ADA_TOOL_PROJECTION_PROVIDER=cosmos\n', encoding='utf-8',
    )
    result = subprocess.run(
        ['docker', 'compose', '--project-directory', str(root),
         '-f', str(root / 'deployment/compose' / f'{profile}.yaml'), 'config', '--format', 'json'],
        cwd=root, capture_output=True, text=True, check=False,
        env={**os.environ, 'ADA_TOOL_NAMESPACE': 'operaciones_integradas'},
    )
    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)
    assert resolved['name'] == f'ada-local-{profile}'
    if profile in ('web', 'full'):
        assert Path(resolved['services']['web']['build']['context']) == root.resolve()
    if profile == 'web':
        assert resolved['services']['web']['environment']['ADA_TOOL_SOURCE_PROVIDER'] == 'blob'
        assert 'resources' not in resolved['services']
        setup = subprocess.run(
            ['docker', 'compose', '--project-directory', str(root),
             '-f', str(root / 'deployment/compose/web.yaml'), '--profile', 'setup',
             'config', '--format', 'json'],
            cwd=root, capture_output=True, text=True, check=False,
            env={**os.environ, 'ADA_TOOL_NAMESPACE': 'operaciones_integradas'},
        )
        assert setup.returncode == 0, setup.stderr
        assert json.loads(setup.stdout)['services']['resources']['environment'][
            'ADA_MANAGER_PERSISTENCE_PROVIDER'
        ] == 'durable'
