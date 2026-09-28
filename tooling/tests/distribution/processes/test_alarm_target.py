from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]


def _load(relative: str, name: str):
    path = _ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tools():
    return (
        _load("deployment/processes/bundle.py", "alarm_target_bundle_test"),
        _load("tooling/distribution/processes/distribute.py", "alarm_target_distribute_test"),
    )


def test_backend_target_discovers_three_independent_alarm_jobs(tools):
    bundle, distribution = tools
    expected = {
        "ada-command-center-alarms-materialization",
        "ada-command-center-alarms-runtime",
        "ada-command-center-alarms-delivery",
    }
    assert set(distribution._target_commands(_ROOT, "ada-command-center-backend")) == expected
    assert {
        bundle.load_container_definition(bundle.load_project(path)).command
        for path in bundle.discover_processes(_ROOT, scope="ada-command-center")
    } == expected


def test_target_and_individual_selection_preserve_other_targets(tools):
    bundle, distribution = tools
    selected = distribution._resolve_selection(
        repository_root=_ROOT,
        bundle=bundle,
        selections=("ada-kpi-runtime", "operational-data-notpii"),
        targets=("ada-command-center-backend",),
    )
    assert [item.deployment.process for item in selected] == [
        "operational-data-notpii",
        "ada-kpi-runtime",
        "ada-command-center-alarms-runtime",
        "ada-command-center-alarms-materialization",
        "ada-command-center-alarms-delivery",
    ]
    individual = distribution._resolve_selection(
        repository_root=_ROOT,
        bundle=bundle,
        selections=("ada-command-center-alarms-delivery",),
        targets=(),
    )
    assert [item.deployment.execution_file for item in individual] == ["alarms-delivery"]


def test_alarm_job_numbers_follow_frozen_operational_classification(tools):
    _, distribution = tools
    catalog = {item.process: int(item.number) for item in distribution.DEPLOYMENT_CATALOG}
    assert catalog["ada-command-center-alarms-runtime"] == 23
    assert catalog["ada-command-center-alarms-materialization"] == 24
    assert catalog["ada-command-center-alarms-delivery"] == 43
    assert all(21 <= catalog[name] <= 40 for name in (
        "ada-command-center-alarms-runtime",
        "ada-command-center-alarms-materialization",
    ))
    assert 41 <= catalog["ada-command-center-alarms-delivery"] <= 60


def test_alarm_transport_dev_groups_require_no_source_only_packages():
    for project in sorted(
        (_ROOT / "scopes/ada-command-center/backend/processes").glob("alarms-*/pyproject.toml")
    ):
        metadata = tomllib.loads(project.read_text(encoding="utf-8"))
        runtime = {
            dependency.partition("==")[0]
            for dependency in metadata["project"]["dependencies"]
        }
        source_only = set(metadata.get("tool", {}).get("uv", {}).get("sources", {})) - runtime
        dev = {
            dependency.partition("==")[0]
            for dependency in metadata.get("dependency-groups", {}).get("dev", [])
            if isinstance(dependency, str)
        }
        assert not dev.intersection(source_only), (
            f"{project}: source-only dev packages cannot be resolved from the transport wheelhouse"
        )
