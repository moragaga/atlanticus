from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[3] / "local/processes/process.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_local_process_tool_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
process_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = process_tool
SPEC.loader.exec_module(process_tool)


def _write_process(
    repository: Path,
    relative: str,
    *,
    command: str,
    project_name: str,
) -> Path:
    root = repository / relative
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{project_name}"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        f'{command} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{command}"\n'
        'system-profile = "base"\n',
        encoding="utf-8",
    )
    return root


class BundleStub:
    def load_project(self, root: Path):
        return root

    def has_container_contract(self, project: Path) -> bool:
        return True

    def load_container_definition(self, project: Path):
        return project

    def resolve_process_root(self, repository_root: Path, value: str) -> Path:
        return repository_root / "resolved" / value


def test_ada_backend_target_resolves_backend_layout(tmp_path: Path) -> None:
    expected = _write_process(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        command="ada-kpi-runtime",
        project_name="ada-kpi-runtime-process",
    )

    roots = process_tool._resolve_target_processes(
        tmp_path, "ada-backend", BundleStub()
    )

    assert roots == (expected,)


def test_operational_data_target_resolves_scope_layout(tmp_path: Path) -> None:
    expected = _write_process(
        tmp_path,
        "scopes/operational-data/processes/notpii",
        command="operational-data-notpii",
        project_name="atlanticus-operational-data-notpii-process",
    )

    roots = process_tool._resolve_target_processes(
        tmp_path,
        "operational-data",
        BundleStub(),
    )

    assert roots == (expected,)


def test_prepare_all_requires_one_logical_target(tmp_path: Path) -> None:
    try:
        process_tool._resolve_prepare_processes(
            tmp_path,
            ("ada-backend", "operational-data"),
            all_target=True,
            bundle=BundleStub(),
        )
    except process_tool.ProcessToolError as error:
        assert str(error) == "prepare --all requires exactly one process target"
    else:
        raise AssertionError("prepare --all accepted multiple targets")


def test_individual_prepare_delegates_process_resolution(tmp_path: Path) -> None:
    roots = process_tool._resolve_prepare_processes(
        tmp_path,
        ("ada-kpi-runtime",),
        all_target=False,
        bundle=BundleStub(),
    )

    assert roots == (tmp_path / "resolved/ada-kpi-runtime",)


def test_public_parser_uses_target_selection_instead_of_scope_flag() -> None:
    arguments = process_tool._parser().parse_args(["prepare", "ada-backend", "--all"])

    assert arguments.action == "prepare"
    assert arguments.selections == ["ada-backend"]
    assert arguments.all is True


def test_commented_process_tool_is_structurally_equivalent() -> None:
    production = ast.dump(
        ast.parse(MODULE_PATH.read_text(encoding="utf-8")),
        include_attributes=False,
    )
    commented = ast.dump(
        ast.parse(
            (MODULE_PATH.parent / "commented/process.py").read_text(encoding="utf-8")
        ),
        include_attributes=False,
    )

    assert production == commented
