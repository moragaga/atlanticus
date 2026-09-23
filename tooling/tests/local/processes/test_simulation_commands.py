from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[3] / "local/processes/process.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_local_process_simulation_parser_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
process_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = process_tool
SPEC.loader.exec_module(process_tool)


def test_simulation_commands_are_explicit() -> None:
    simulate = process_tool._parser().parse_args(["simulate", "--bind"])
    stop = process_tool._parser().parse_args(["simulate-stop"])

    assert simulate.action == "simulate"
    assert simulate.bind is True
    assert stop.action == "simulate-stop"
