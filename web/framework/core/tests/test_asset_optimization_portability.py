from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from atlanticus.web.asset_optimization import optimize_staged_assets
from atlanticus.web.errors import WebAssetError

ROOT = Path(__file__).resolve().parents[1]


def test_native_windows_excludes_binary_minifiers_without_excluding_linux():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    dependencies = project['project']['dependencies']
    minifiers = {
        dependency.name: dependency
        for item in dependencies
        if (dependency := Requirement(item)).name in {'rcssmin', 'rjsmin'}
    }
    assert set(minifiers) == {'rcssmin', 'rjsmin'}
    for requirement in minifiers.values():
        assert requirement.marker is not None
        assert not requirement.marker.evaluate({'sys_platform': 'win32'})
        assert requirement.marker.evaluate({'sys_platform': 'linux'})
        assert requirement.marker.evaluate({'sys_platform': 'darwin'})


def test_unoptimized_asset_module_does_not_require_minifiers(monkeypatch):
    monkeypatch.setitem(sys.modules, 'rcssmin', None)
    monkeypatch.setitem(sys.modules, 'rjsmin', None)
    import atlanticus.web.asset_optimization as optimization
    assert callable(optimization.optimize_staged_assets)


def test_css_optimization_fails_explicitly_if_minifier_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'rcssmin', None)
    source = tmp_path / 'style.css'
    source.write_text('body { color: red; }', encoding='utf-8')
    with pytest.raises(WebAssetError, match='require rcssmin'):
        optimize_staged_assets(tmp_path, {'css_entries': ['style.css'], 'js_entries': []})
    assert source.is_file()


def test_js_optimization_fails_explicitly_if_minifier_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'rjsmin', None)
    source = tmp_path / 'code.js'
    source.write_text('const x = 1;', encoding='utf-8')
    with pytest.raises(WebAssetError, match='require rjsmin'):
        optimize_staged_assets(tmp_path, {'css_entries': [], 'js_entries': ['code.js']})
    assert source.read_text(encoding='utf-8') == 'const x = 1;'


def test_pedagogical_mirror_matches_production():
    source = ast.dump(ast.parse((ROOT / 'src/atlanticus/web/asset_optimization.py').read_text()), include_attributes=False)
    mirror = ast.dump(ast.parse((ROOT / 'commented/atlanticus/web/asset_optimization.py').read_text()), include_attributes=False)
    assert source == mirror
