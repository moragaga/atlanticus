from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE = Path(__file__).resolve().parents[3] / "distribution/processes/distribute.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_process_connections_distribution", MODULE
)
assert SPEC is not None and SPEC.loader is not None
distribution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = distribution
SPEC.loader.exec_module(distribution)


def test_configured_file_is_not_packaged_and_is_preserved_during_update(tmp_path):
    process_root = tmp_path / "target/processes/kpis-materialization"
    config = process_root / "config"
    config.mkdir(parents=True)
    (config / "connections.json").write_text('{"schema_version":1}', encoding="utf-8")
    staged = tmp_path / "stage/processes/kpis-materialization"
    (staged / "config").mkdir(parents=True)
    (staged / "config/connections.detail.json").write_text("{}", encoding="utf-8")
    assert "connections.json" in distribution._artifact_ignore(
        str(config), ["connections.detail.json", "connections.json"]
    )
    distribution._preserve_consumer_configuration(
        tmp_path / "target", staged, "kpis-materialization"
    )
    assert (staged / "config/connections.json").read_text(encoding="utf-8") == (
        '{"schema_version":1}'
    )


def test_direct_compose_mounts_config_only_if_template_is_present(tmp_path):
    path = tmp_path / "config"
    path.mkdir()
    (path / "connections.detail.json").write_text("{}", encoding="utf-8")
    artifact = SimpleNamespace(root=tmp_path, cpus=0.5, memory="1g")
    deployment = distribution.ProcessDeployment(
        "23", "ada-kpi-materialization", "kpis-materialization"
    )
    selected = SimpleNamespace(artifact=artifact, deployment=deployment)
    compose = distribution._render_service("test", selected, volume_mode="named")
    assert (
        "../../processes/kpis-materialization/config:/app/process/config:ro" in compose
    )
    (path / "connections.detail.json").unlink()
    compose = distribution._render_service("test", selected, volume_mode="named")
    assert "/app/process/config" not in compose
