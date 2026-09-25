from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "bundle.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_deployment_process_provenance_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)


def _write_project(
    root: Path,
    *,
    name: str,
    dependencies: tuple[str, ...] = (),
    command: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    dependency_lines = "".join(f'    "{item}",\n' for item in dependencies)
    scripts = ""
    container = ""
    if command is not None:
        scripts = f'\n[project.scripts]\n{command} = "sample:main"\n'
        container = (
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
        'description = "Sample project."\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = [\n"
        f"{dependency_lines}"
        "]\n"
        f"{scripts}"
        f"{container}",
        encoding="utf-8",
    )
    source = root / "src/sample"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")


def test_fingerprint_tracks_process_and_internal_dependency_inputs(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    process = repository / "scopes/operational-data/processes/sample"
    dependency = repository / "backend/dependency"
    _write_project(
        process,
        name="sample-process",
        dependencies=("atlanticus-dependency==1.0.0",),
        command="operational-data-sample",
    )
    _write_project(dependency, name="atlanticus-dependency")

    initial = bundle.process_build_inputs_fingerprint(repository, process)

    (process / ".env").write_text("SECRET=local\n", encoding="utf-8")
    assert bundle.process_build_inputs_fingerprint(repository, process) == initial

    process_source = process / "src/sample/__init__.py"
    process_source.write_text("VALUE = 2\n", encoding="utf-8")
    assert bundle.process_build_inputs_fingerprint(repository, process) != initial

    process_source.write_text("VALUE = 1\n", encoding="utf-8")
    dependency_source = dependency / "src/sample/__init__.py"
    dependency_source.write_text("VALUE = 2\n", encoding="utf-8")
    assert bundle.process_build_inputs_fingerprint(repository, process) != initial


def test_prepare_receipt_is_independent_from_mutable_qa_artifact(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    process = repository / "scopes/operational-data/processes/sample"
    _write_project(process, name="sample-process", command="operational-data-sample")
    fingerprint = bundle.process_build_inputs_fingerprint(repository, process)

    receipt = bundle.write_prepare_receipt(repository, process, fingerprint)
    qa_artifact = repository / "artifacts/processes/operational-data-sample/src"
    qa_artifact.mkdir(parents=True)
    (qa_artifact / "manual-change.py").write_text("VALUE = 99\n", encoding="utf-8")

    assert bundle.require_prepared_build_inputs(repository, process) == receipt
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["process"] == "operational-data-sample"
    assert payload["build_inputs_fingerprint"] == fingerprint


def test_prepare_receipt_blocks_changed_source(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    process = repository / "scopes/operational-data/processes/sample"
    _write_project(process, name="sample-process", command="operational-data-sample")
    fingerprint = bundle.process_build_inputs_fingerprint(repository, process)
    bundle.write_prepare_receipt(repository, process, fingerprint)

    (process / "src/sample/__init__.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(
        bundle.ProcessBundleError, match="prepared build inputs are stale"
    ):
        bundle.require_prepared_build_inputs(repository, process)
