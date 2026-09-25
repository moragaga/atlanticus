from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "distribution/processes/consumer/process.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_consumer_simulation_parser_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consumer
SPEC.loader.exec_module(consumer)


def test_distribution_simulation_commands_are_explicit() -> None:
    simulate = consumer._parser().parse_args(["simulate", "--bind"])
    stop = consumer._parser().parse_args(["simulate-stop"])

    assert simulate.action == "simulate"
    assert simulate.bind is True
    assert stop.action == "simulate-stop"


def test_distribution_compose_files_live_under_deployment_local(tmp_path: Path) -> None:
    assert consumer._compose_file(tmp_path, bind=False) == (
        tmp_path / "deployment/local/compose.yaml"
    )
    assert consumer._compose_file(tmp_path, bind=True) == (
        tmp_path / "deployment/local/compose.bind.yaml"
    )
