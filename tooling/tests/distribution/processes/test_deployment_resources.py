from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "distribution/processes/consumer/deployment_resources.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_deployment_resources_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
resources = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resources
SPEC.loader.exec_module(resources)

PAIRS = tuple((step / 4, step / 2) for step in range(1, 17))


@pytest.mark.parametrize(("vcpu", "memory_gib"), PAIRS)
def test_all_supported_azure_pairs_translate_to_docker_mib(
    tmp_path: Path, vcpu: float, memory_gib: float
) -> None:
    path = tmp_path / "deployment.resources.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "processes": {"sample": {"vcpu": vcpu, "memory_gib": memory_gib}},
            }
        ),
        encoding="utf-8",
    )

    loaded = resources.require_resources(path, ("sample",))

    assert resources.docker_memory(loaded["sample"]) == f"{int(memory_gib * 1024)}m"


def test_invalid_cpu_memory_pair_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "deployment.resources.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "processes": {"sample": {"vcpu": 1.25, "memory_gib": 3.0}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(resources.DeploymentResourcesError, match="must be 2.5 GiB"):
        resources.require_resources(path, ("sample",))


def test_distribution_process_set_must_match_resource_set(tmp_path: Path) -> None:
    path = tmp_path / "deployment.resources.json"
    resources.write_resources(
        path,
        {"sample": resources.default_resources()},
    )

    with pytest.raises(resources.DeploymentResourcesError, match="missing: other"):
        resources.require_resources(path, ("sample", "other"))
