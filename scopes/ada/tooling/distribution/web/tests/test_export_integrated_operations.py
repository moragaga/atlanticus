from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import types
import zipfile
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[1]


def _load_exporter(monkeypatch: pytest.MonkeyPatch):
    generator = types.ModuleType('generate_starter')
    generator._copy_product_files = lambda source, destination, excluded_roots=(): shutil.copytree(
        source, destination, dirs_exist_ok=True
    )
    generator._environment_entries = lambda path: path.read_text(encoding='utf-8')
    generator._mapping = lambda entries, environment: environment + '\n' + entries
    generator._secrets = lambda entries: '[]\n'
    builder = types.ModuleType('build_distribution')
    builder.AdaDistributionError = RuntimeError
    builder._build_internal = lambda **kwargs: []
    builder._build_project_tooling = lambda **kwargs: {}
    builder._sha256 = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    builder._write_external_requirements = lambda **kwargs: None
    builder._write_host_requirements = lambda **kwargs: None
    builder._write_starter_build_requirements = lambda **kwargs: None
    builder.wheels = types.SimpleNamespace()
    qualifier = types.ModuleType('qualify_distribution')
    qualifier.qualify_ada_distribution = lambda path: {'status': 'PRECHECK_PASS'}
    for name, module in (
        ('generate_starter', generator),
        ('build_distribution', builder),
        ('qualify_distribution', qualifier),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        'integrated_export_test', TOOL_ROOT / 'export_integrated_operations.py'
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_contracts(module):
    specialized = []
    generic = ['# Additional variables from ADA Generic']
    for name, mode in module.MODES.items():
        if name == 'ATLANTICUS_WEB_ASSETS_OPTIMIZED':
            generic.append('# ATLANTICUS_WEB_ASSETS_OPTIMIZED=true')
            continue
        if mode.startswith('key-vault'):
            specialized.append(f'# {name}=<secret>')
        elif mode == 'environment':
            specialized.append(f'{name}=local')
        elif name == 'ADA_TOOL_ADOPTION_MODE':
            specialized.append(f'{name}=startup')
        elif mode == 'manual-default':
            specialized.append(f'{name}=operaciones_integradas' if name == 'ADA_TOOL_NAMESPACE' else f'{name}=false')
        else:
            specialized.append(f'# {name}=test')
    return '\n'.join(specialized), '\n'.join(generic)


def test_environment_documentation_includes_hidden_and_generic_options(monkeypatch):
    module = _load_exporter(monkeypatch)
    specialized, generic = _fixture_contracts(module)
    readable, normalized = module._environment_contract(specialized, generic)
    for name in module.MODES:
        assert readable.count(f'{name}=') == 1
        assert normalized.count(f'{name}=') == 1
    assert '# ADA_STORAGE_SAS_TOKEN=test' in readable
    assert '# COSMOS_CONSUMPTION_KEY=test' in readable
    assert '# ATLANTICUS_WEB_ASSETS_OPTIMIZED=true' in readable
    assert 'ADA_STORAGE_CONNECTION_STRING=<secret>' in normalized
    assert 'COSMOS_CONSUMPTION_KEY=' in normalized
    assert 'ATLANTICUS_WEB_PORT=' in normalized
    assert 'ADA_TOOL_NAMESPACE=operaciones_integradas' in normalized
    assert 'ADA_TOOL_ADOPTION_MODE=startup' in normalized


def test_environment_contract_rejects_missing_configuration(monkeypatch):
    module = _load_exporter(monkeypatch)
    specialized, generic = _fixture_contracts(module)
    with pytest.raises(ValueError, match='Missing documented environment variables'):
        module._environment_contract(specialized, '')
    with pytest.raises(ValueError, match='Duplicate environment variable'):
        module._environment_contract(specialized + '\nADA_PERSISTENCE_MODE=local', generic)
    with pytest.raises(ValueError, match='Undeclared environment variables'):
        module._environment_contract(specialized + '\nNEW_UNKNOWN_OPTION=true', generic)


def test_environment_contract_exports_both_adoption_modes(monkeypatch):
    module = _load_exporter(monkeypatch)
    specialized, generic = _fixture_contracts(module)
    assert module.MODES['ADA_TOOL_ADOPTION_MODE'] == 'manual-default'
    _, default = module._environment_contract(specialized, generic)
    assert 'ADA_TOOL_ADOPTION_MODE=startup' in default

    on_page_load = specialized.replace(
        'ADA_TOOL_ADOPTION_MODE=startup', 'ADA_TOOL_ADOPTION_MODE=on_page_load'
    )
    _, configured = module._environment_contract(on_page_load, generic)
    assert 'ADA_TOOL_ADOPTION_MODE=on_page_load' in configured


def test_environment_contract_rejects_invalid_adoption_mode(monkeypatch):
    module = _load_exporter(monkeypatch)
    specialized, generic = _fixture_contracts(module)
    invalid = specialized.replace('ADA_TOOL_ADOPTION_MODE=startup', 'ADA_TOOL_ADOPTION_MODE=invalid')
    with pytest.raises(ValueError, match='ADA_TOOL_ADOPTION_MODE'):
        module._environment_contract(invalid, generic)


def test_portable_pyproject_keeps_entrypoint_and_packages(monkeypatch):
    module = _load_exporter(monkeypatch)
    original = '''[project]
name = "ada-integrated-operations-application"
version = "0.1.2"
[project.scripts]
ada-integrated-operations-application = "ada.web.application.integrated_operations.__main__:main"
[tool.uv.sources]
example={path="../../../example",editable=true}
[tool.setuptools.packages.find]
include = ["ada.web.application.integrated_operations*"]
'''
    result = module._portable_pyproject(original)
    assert '[tool.uv.sources]' not in result
    assert 'include = ["ada.web.application.integrated_operations*", "application*"]' in result
    assert 'ada-integrated-operations-application = ' in result


def test_starter_exports_editable_root_without_tests_or_commentary(monkeypatch, tmp_path):
    module = _load_exporter(monkeypatch)
    project = tmp_path / 'original'
    generic = tmp_path / 'generic'
    base = tmp_path / 'base'
    overlay = tmp_path / 'overlay'
    project.mkdir()
    generic.mkdir()
    (base / 'src/application').mkdir(parents=True)
    (overlay / 'src/application').mkdir(parents=True)
    (base / 'src/application/composition.py').write_text('LEGACY\n', encoding='utf-8')
    (overlay / 'src/application/wsgi.py').write_text('application = None\n', encoding='utf-8')
    (project / 'src/ada/web/application/integrated_operations').mkdir(parents=True)
    (project / 'src/ada/web/application/integrated_operations/__main__.py').write_text(
        'def main(): pass\n', encoding='utf-8'
    )
    (project / 'tests').mkdir()
    (project / 'tests/test_ui.py').write_text('assert False\n', encoding='utf-8')
    (project / 'commented').mkdir()
    (project / 'commented/demo.py').write_text('old\n', encoding='utf-8')
    (project / 'pyproject.toml').write_text(
        '[project]\nname="ada-integrated-operations-application"\nversion="0.1.2"\n'
        '[tool.uv.sources]\nexample={path="../example",editable=true}\n'
        '[tool.setuptools.packages.find]\n'
        'include = ["ada.web.application.integrated_operations*"]\n', encoding='utf-8'
    )
    specialized, generic_contract = _fixture_contracts(module)
    (project / '.env.detail').write_text(specialized, encoding='utf-8')
    (generic / '.env.detail').write_text(generic_contract, encoding='utf-8')
    monkeypatch.setattr(module, 'PROJECT_ROOT', project)
    monkeypatch.setattr(module, 'GENERIC_ROOT', generic)
    monkeypatch.setattr(module, 'BASE_STARTER', base)
    monkeypatch.setattr(module, 'ADA_STARTER', overlay)
    export = tmp_path / 'exported'
    module._starter(export)
    assert (export / 'src/ada/web/application/integrated_operations/__main__.py').is_file()
    assert 'create_integrated_operations_extension' in (export / 'src/application/runtime.py').read_text()
    assert not (export / 'src/application/composition.py').exists()
    assert not (export / 'tests').exists()
    assert not (export / 'commented').exists()
    assert not (export / 'development').exists()
    assert '.env' in (export / '.gitignore').read_text().splitlines()
    assert not (export / 'tooling/commented').exists()
    assert (export / 'tooling/run_local.sh').is_file()
    assert (export / 'tooling/install_local.sh').is_file()
    assert (export / 'configuration/templates/prd.mapping-env.csv').is_file()
    assert 'COSMOS_CONSUMPTION_ENDPOINT=' in (
        export / 'configuration/templates/prd.mapping-env.csv'
    ).read_text()
    assert '# ATLANTICUS_WEB_ASSETS_OPTIMIZED=true' in (export / '.env.detail').read_text()
    assert '[tool.uv.sources]' not in (export / 'pyproject.toml').read_text()
    assert '[tool.uv.sources]' in (project / 'pyproject.toml').read_text()
    manifest = json.loads((export / 'manifest.json').read_text(encoding='utf-8'))
    assert 'src/ada/web/application/integrated_operations/__main__.py' in manifest['files']
    assert manifest['editable_source'] == 'src'


def test_wheel_asset_inventory_accepts_complete_manifest(monkeypatch, tmp_path):
    module = _load_exporter(monkeypatch)
    wheel = tmp_path / 'atlanticus_web_users-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('atlanticus/web/users/resources/css/css.list', '00_users_admin.css\n')
        archive.writestr('atlanticus/web/users/resources/css/00_users_admin.css', 'body {}')
    module._validate_packaged_asset_lists(tmp_path)


def test_wheel_asset_inventory_rejects_unlisted_css(monkeypatch, tmp_path):
    module = _load_exporter(monkeypatch)
    wheel = tmp_path / 'atlanticus_web_users-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('atlanticus/web/users/resources/css/css.list', '00_users_admin.css\n')
        archive.writestr('atlanticus/web/users/resources/css/00_users_admin.css', 'body {}')
        archive.writestr('atlanticus/web/users/resources/css/10_users_projection.css', 'main {}')
    with pytest.raises(RuntimeError, match='10_users_projection.css'):
        module._validate_packaged_asset_lists(tmp_path)


def test_wheel_asset_inventory_rejects_duplicate_declaration(monkeypatch, tmp_path):
    module = _load_exporter(monkeypatch)
    wheel = tmp_path / 'users-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('atlanticus/web/users/resources/css/css.list', '00_users_admin.css\n00_users_admin.css\n')
        archive.writestr('atlanticus/web/users/resources/css/00_users_admin.css', 'body {}')
    with pytest.raises(RuntimeError, match='duplicates=1'):
        module._validate_packaged_asset_lists(tmp_path)


def test_productive_sources_match_pedagogical_mirrors():
    original = TOOL_ROOT / 'export_integrated_operations.py'
    commented = TOOL_ROOT / 'commented/export_integrated_operations.py'
    assert ast.dump(ast.parse(original.read_text()), include_attributes=False) == (
        ast.dump(ast.parse(commented.read_text()), include_attributes=False)
    )
