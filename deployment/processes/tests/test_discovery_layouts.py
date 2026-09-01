from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "bundle.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_deployment_process_bundle_layouts",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)

ProcessBundleError = bundle.ProcessBundleError
discover_processes = bundle.discover_processes
resolve_process_root = bundle.resolve_process_root


def test_discovery_supports_classic_and_backend_process_layouts(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    classic = repository / "scopes" / "operational-data" / "processes" / "pi"
    backend = repository / "scopes" / "ada" / "backend" / "processes" / "kpi-runtime"
    _write_project(
        classic,
        name="atlanticus-operational-data-pi-process",
        command="operational-data-pi",
    )
    _write_project(
        backend,
        name="ada-kpi-runtime-process",
        command="ada-kpi-runtime",
    )

    assert discover_processes(repository) == tuple(sorted((classic, backend)))
    assert discover_processes(repository, scope="operational-data") == (classic,)
    assert discover_processes(repository, scope="ada") == (backend,)


def test_backend_layout_named_resolution_accepts_command_and_package_name(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    backend = repository / "scopes" / "ada" / "backend" / "processes" / "kpi-historian"
    _write_project(
        backend,
        name="ada-kpi-historian-process",
        command="ada-kpi-historian",
    )

    assert (
        resolve_process_root(
            repository,
            "ada-kpi-historian",
            scope="ada",
        )
        == backend
    )
    assert (
        resolve_process_root(
            repository,
            "ada-kpi-historian-process",
            scope="ada",
        )
        == backend
    )


def test_discovery_does_not_recurse_into_unapproved_nested_process_layouts(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    backend = repository / "scopes" / "ada" / "backend" / "processes" / "kpi-delivery"
    nested = (
        repository
        / "scopes"
        / "ada"
        / "backend"
        / "internal"
        / "processes"
        / "not-a-composition-root"
    )
    _write_project(
        backend,
        name="ada-kpi-delivery-process",
        command="ada-kpi-delivery",
    )
    _write_project(
        nested,
        name="unexpected-process",
        command="unexpected-process",
    )

    assert discover_processes(repository, scope="ada") == (backend,)


def test_duplicate_container_command_fails_before_artifact_generation(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    classic = repository / "scopes" / "sample" / "processes" / "classic"
    backend = repository / "scopes" / "sample" / "backend" / "processes" / "backend"
    _write_project(
        classic,
        name="classic-process",
        command="shared-command",
    )
    _write_project(
        backend,
        name="backend-process",
        command="shared-command",
    )

    with pytest.raises(
        ProcessBundleError, match="duplicate process container command shared-command"
    ):
        discover_processes(repository, scope="sample")


def test_project_without_container_contract_is_not_exportable_in_either_layout(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    classic = repository / "scopes" / "sample" / "processes" / "library"
    backend = repository / "scopes" / "sample" / "backend" / "processes" / "runtime"
    _write_project(classic, name="sample-library")
    _write_project(
        backend,
        name="sample-runtime",
        command="sample-runtime",
    )

    assert discover_processes(repository, scope="sample") == (backend,)


def _write_project(
    root: Path,
    *,
    name: str,
    command: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    script_section = ""
    container_section = ""
    if command is not None:
        script_section = f'\n[project.scripts]\n{command} = "sample:main"\n'
        container_section = (
            "\n[tool.atlanticus.container]\n"
            f'command = "{command}"\n'
            'system-profile = "base"\n'
        )
    (root / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools==83.0.0"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{name}"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        'classifiers = ["Private :: Do Not Upload"]\n'
        "dependencies = []\n"
        f"{script_section}"
        f"{container_section}",
        encoding="utf-8",
    )
