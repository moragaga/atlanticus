from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PYTHON_VERSION = (3, 14, 2)
PROCESS_BUNDLE_MODULE = "atlanticus_deployment_process_bundle_check"


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    deployment: Path
    scripts: Path


def _paths() -> Paths:
    for root in Path(__file__).resolve().parents:
        if (root / "deployment").is_dir() and (root / "scripts").is_dir():
            return Paths(
                root=root, deployment=root / "deployment", scripts=root / "scripts"
            )
    raise RuntimeError("Atlanticus repository root could not be resolved")


def _run(command: list[str], *, cwd: Path) -> None:
    print("> " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _validate_python() -> None:
    if sys.version_info[:3] != PYTHON_VERSION:
        actual = ".".join(str(item) for item in sys.version_info[:3])
        expected = ".".join(str(item) for item in PYTHON_VERSION)
        raise RuntimeError(f"Python {expected} is required, found {actual}")


def _validate_structure(paths: Paths) -> None:
    required = (
        paths.deployment / "processes" / "Dockerfile",
        paths.deployment / "processes" / ".dockerignore",
        paths.deployment / "processes" / "bundle.py",
        paths.deployment / "processes" / "commented" / "bundle.py",
        paths.deployment / "local" / "generate_compose.py",
        paths.deployment / "local" / "commented" / "generate_compose.py",
        paths.scripts / "local-process.sh",
        paths.scripts / "commented" / "local-process.sh",
    )
    missing = tuple(path for path in required if not path.is_file())
    if missing:
        raise RuntimeError(f"Deployment file not found: {missing[0]}")
    retired = paths.root / "scopes" / "ada" / "scripts" / "processes"
    if retired.exists():
        raise RuntimeError(f"Retired ADA process tooling still exists: {retired}")


def _load_process_bundle(paths: Paths):
    module_path = paths.deployment / "processes" / "bundle.py"
    spec = importlib.util.spec_from_file_location(PROCESS_BUNDLE_MODULE, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Process bundle module could not be loaded: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_process_contracts(paths: Paths) -> None:
    bundle = _load_process_bundle(paths)
    expected_python = f"=={'.'.join(str(item) for item in PYTHON_VERSION)}"
    try:
        process_roots = bundle.discover_processes(paths.root)
        for process_root in process_roots:
            project = bundle.load_project(process_root)
            if project.requires_python != expected_python:
                raise RuntimeError(
                    f"Process must require Python {expected_python.removeprefix('==')}: "
                    f"{process_root / 'pyproject.toml'}"
                )
    except bundle.ProcessBundleError as error:
        raise RuntimeError(
            f"Process container contract validation failed: {error}"
        ) from error


def _validate_docker_contract(paths: Paths) -> None:
    dockerfile = (paths.deployment / "processes" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    dockerignore = (paths.deployment / "processes" / ".dockerignore").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "COPY processes/${FILENAME}/ ./",
        "config.json",
        "secrets.json",
        ".env",
    )
    for value in forbidden:
        if value in dockerfile:
            raise RuntimeError(f"Active configuration may reach process image: {value}")
    required = (
        "COPY processes/${FILENAME}/pyproject.toml processes/${FILENAME}/uv.lock ./",
        "COPY processes/${FILENAME}/wheels ./wheels",
        "COPY processes/${FILENAME}/src ./src",
    )
    for value in required:
        if value not in dockerfile:
            raise RuntimeError(f"Docker transport COPY contract is missing: {value}")
    if "!processes/**" in dockerignore:
        raise RuntimeError("Docker context must not expose complete process artifacts")
    for value in (
        "!processes/*/pyproject.toml",
        "!processes/*/uv.lock",
        "!processes/*/wheels/**",
        "!processes/*/src/**",
    ):
        if value not in dockerignore:
            raise RuntimeError(f"Docker context allowlist is missing: {value}")


def _validate_python_mirror(production: Path, commented: Path) -> None:
    production_ast = ast.dump(
        ast.parse(production.read_text(encoding="utf-8")), include_attributes=False
    )
    commented_ast = ast.dump(
        ast.parse(commented.read_text(encoding="utf-8")), include_attributes=False
    )
    if production_ast != commented_ast:
        raise RuntimeError(f"Commented mirror differs semantically: {commented}")


def _validate_mirrors(paths: Paths) -> None:
    _validate_python_mirror(
        paths.deployment / "processes" / "bundle.py",
        paths.deployment / "processes" / "commented" / "bundle.py",
    )
    _validate_python_mirror(
        paths.deployment / "local" / "generate_compose.py",
        paths.deployment / "local" / "commented" / "generate_compose.py",
    )
    _validate_python_mirror(
        paths.scripts / "deployment" / "check.py",
        paths.scripts / "commented" / "deployment" / "check.py",
    )


def main() -> None:
    paths = _paths()
    print("[1/8] Validating Python runtime")
    _validate_python()
    print("[2/8] Validating deployment ownership and structure")
    _validate_structure(paths)
    print("[3/8] Validating exportable process container contracts")
    _validate_process_contracts(paths)
    print("[4/8] Validating Docker transport boundary")
    _validate_docker_contract(paths)
    print("[5/8] Applying safe Ruff fixes and formatting")
    targets = [
        "deployment/processes/bundle.py",
        "deployment/processes/commented/bundle.py",
        "deployment/processes/tests",
        "deployment/local/generate_compose.py",
        "deployment/local/commented/generate_compose.py",
        "deployment/local/tests",
        "scripts/deployment/check.py",
        "scripts/commented/deployment/check.py",
    ]
    _run(["ruff", "check", "--fix", *targets], cwd=paths.root)
    _run(["ruff", "format", *targets], cwd=paths.root)
    _run(["ruff", "check", *targets], cwd=paths.root)
    _run(["ruff", "format", "--check", *targets], cwd=paths.root)
    print("[6/8] Running deployment tooling tests")
    _run([sys.executable, "-m", "pytest", "deployment/processes/tests"], cwd=paths.root)
    _run([sys.executable, "-m", "pytest", "deployment/local/tests"], cwd=paths.root)
    print("[7/8] Validating productive/commented semantic mirrors")
    _validate_mirrors(paths)
    print("[8/8] Validating shell wrappers")
    _run(["bash", "-n", "scripts/local-process.sh"], cwd=paths.root)
    _run(["bash", "-n", "scripts/commented/local-process.sh"], cwd=paths.root)
    print("Atlanticus process deployment flow validated")


if __name__ == "__main__":
    main()
