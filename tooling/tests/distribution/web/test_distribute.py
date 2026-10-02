from __future__ import annotations

import ast
import importlib.util
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

_TOOL = Path(__file__).resolve().parents[3] / "distribution/web/distribute.py"
_spec = importlib.util.spec_from_file_location("distribute_web", _TOOL)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)


def test_generic_distribution_runs_shared_pipeline_in_order(
    tmp_path, monkeypatch
) -> None:
    calls: list[str] = []
    destination = tmp_path / "generic"

    def generate(*, profile, destination):
        calls.append("starter")
        destination.mkdir()
        return destination

    def build(*, profile, application, uv):
        calls.append("distribution")
        return {"status": "BUILT_UNQUALIFIED", "profile": profile}

    def qualify(**kwargs):
        calls.append("qualification")
        assert kwargs["portable"] is True
        assert kwargs["inspect_only"] is False
        return {"status": "PASS", "profile": kwargs["profile"]}

    monkeypatch.setattr(_module, "generate_starter", generate)
    monkeypatch.setattr(_module, "build_wheelhouse", build)
    monkeypatch.setattr(_module, "qualify", qualify)

    result = _module.build_web_distribution(
        profile="generic",
        destination=destination,
        uv="uv",
        python=Path(sys.executable),
        timeout=90,
    )

    assert result["status"] == "PASS"
    assert calls == ["starter", "distribution", "qualification"]


def test_ada_distribution_uses_existing_specialized_builder(
    tmp_path, monkeypatch
) -> None:
    calls: list[str] = []
    destination = tmp_path / "ada"

    def generate(*, profile, destination):
        calls.append("starter")
        destination.mkdir()
        return destination

    builder = SimpleNamespace(
        build_ada_distribution=lambda **kwargs: (
            calls.append("distribution")
            or {
                "status": "BUILT_UNQUALIFIED",
                "profile": "ada",
            }
        )
    )

    def qualify(*, application, timeout):
        calls.append("qualification")
        return {"status": "PRECHECK_PASS", "profile": "ada"}

    monkeypatch.setattr(_module, "generate_starter", generate)
    monkeypatch.setattr(_module, "_load_ada_builder", lambda: builder)
    monkeypatch.setattr(_module, "_qualify_ada_distribution", qualify)
    monkeypatch.setattr(
        _module,
        "build_wheelhouse",
        lambda **kwargs: pytest.fail("ADA must not use the generic wheelhouse builder"),
    )

    result = _module.build_web_distribution(
        profile="ada",
        destination=destination,
        uv="uv",
        python=Path(sys.executable),
        timeout=90,
    )

    assert result["status"] == "PRECHECK_PASS"
    assert calls == ["starter", "distribution", "qualification"]


def test_failed_stage_is_reported_without_hiding_completed_stages(
    tmp_path, monkeypatch
) -> None:
    destination = tmp_path / "generic"

    def generate(*, profile, destination):
        destination.mkdir()
        return destination

    monkeypatch.setattr(_module, "generate_starter", generate)
    monkeypatch.setattr(
        _module,
        "build_wheelhouse",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("distribution failed")),
    )

    result = _module.build_web_distribution(
        profile="generic",
        destination=destination,
        uv="uv",
        python=Path(sys.executable),
        timeout=90,
    )

    assert result["status"] == "BLOCKED"
    assert result["failed_stage"] == "distribution"
    assert result["stages"]["starter"]["status"] == "PASS"
    assert result["error"] == "distribution failed"


def test_qualification_failure_is_preserved(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "generic"

    def generate(*, profile, destination):
        destination.mkdir()
        return destination

    monkeypatch.setattr(_module, "generate_starter", generate)
    monkeypatch.setattr(
        _module,
        "build_wheelhouse",
        lambda **kwargs: {"status": "BUILT_UNQUALIFIED", "profile": "generic"},
    )
    monkeypatch.setattr(
        _module,
        "qualify",
        lambda **kwargs: {"status": "FAIL", "profile": "generic"},
    )

    result = _module.build_web_distribution(
        profile="generic",
        destination=destination,
        uv="uv",
        python=Path(sys.executable),
        timeout=90,
    )

    assert result["status"] == "FAIL"
    assert result["failed_stage"] == "qualification"


def test_ada_starter_root_dependency_matches_current_application() -> None:
    repository = _TOOL.parents[3]
    starter = tomllib.loads(
        (repository / "tooling/distribution/web/starter/ada/pyproject.toml").read_text()
    )
    application = tomllib.loads(
        (
            repository
            / "scopes/ada/web/application/ada-generic-application/pyproject.toml"
        ).read_text()
    )
    expected = f"ada-generic-application=={application['project']['version']}"
    assert expected in starter["project"]["dependencies"]


def test_distributor_commented_mirror_is_ast_equivalent() -> None:
    productive = ast.dump(ast.parse(_TOOL.read_text()), include_attributes=False)
    commented = ast.dump(
        ast.parse((_TOOL.parent / "commented/distribute.py").read_text()),
        include_attributes=False,
    )
    assert productive == commented
