from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

# Contrato de ejecución del tooling distribuido. Se mantiene junto al proyecto, no al runtime ADA.
PYTHON_VERSION = "3.14.2"
LOCK_SCHEMA = 1
DEPENDENCY_NAME = re.compile(
    r"^([A-Za-z][A-Za-z0-9_.-]*)(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|~=|!=|>=|<=|>|<)\s*[0-9][A-Za-z0-9.*+!_-]*)?"
    r"(?:\s*,\s*(?:==|~=|!=|>=|<=|>|<)\s*[0-9][A-Za-z0-9.*+!_-]*)*$"
)
COMPOSE_PROFILES = frozenset({"web", "infra", "full"})
COMPOSE_ACTIONS = frozenset({"up", "down", "logs", "ps", "build", "prepare"})
_COMPOSE_NETWORK_DEFAULT = "ada-generic-support"
_COMPOSE_PROJECTS = {"infra": "ada-local-infra", "web": "ada-local-web", "full": "ada-local-full"}


class ProjectError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# La huella invalida el sync cuando cambia código editable de la Tool.
def _starter_source_digest(root: Path) -> str:
    source = root / "src"
    files = sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and not {"__pycache__"} & set(path.relative_to(source).parts)
        and not any(part.endswith(".egg-info") for part in path.relative_to(source).parts)
        and path.suffix != ".pyc"
    )
    if not files:
        raise ProjectError("ADA Starter source is missing")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha(path)))
    return digest.hexdigest()


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _dependency_name(specification: str) -> str:
    if any(character in specification for character in ("\n", "\r", "#", "@", "\\", "/")):
        raise ProjectError("Only named registry dependencies are supported")
    match = DEPENDENCY_NAME.fullmatch(specification.strip())
    if match is None:
        raise ProjectError(f"Invalid named registry dependency: {specification}")
    return _canonical(match[1])


def _read_project(root: Path) -> tuple[dict, list[str]]:
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("dependencies"), list):
        raise ProjectError("Project dependencies are missing from pyproject.toml")
    dependencies = project["dependencies"]
    if not all(isinstance(item, str) for item in dependencies):
        raise ProjectError("Project dependency declarations must be strings")
    return metadata, dependencies


def _internal_versions(root: Path) -> dict[str, str]:
    metadata = json.loads((root / "wheelhouse/manifest.json").read_text(encoding="utf-8"))
    packages = metadata.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ProjectError("Internal wheelhouse manifest is incomplete")
    versions = {_canonical(item["name"]): item["version"] for item in packages}
    if len(versions) != len(packages):
        raise ProjectError("Internal wheelhouse contains duplicate package identities")
    return versions


def _external_dependencies(root: Path, dependencies: list[str]) -> list[str]:
    internal = _internal_versions(root)
    required = internal.get("ada-generic-application")
    if required is None:
        raise ProjectError("ADA Generic internal wheel is missing")
    external: list[str] = []
    names: set[str] = set()
    root_count = 0
    for declaration in dependencies:
        name = _dependency_name(declaration)
        if name in names:
            raise ProjectError(f"Duplicate project dependency: {name}")
        names.add(name)
        if name in internal:
            if name != "ada-generic-application" or declaration != f"{name}=={required}":
                raise ProjectError(f"Internal distribution package cannot be changed: {name}")
            root_count += 1
        else:
            external.append(declaration)
    if root_count != 1:
        raise ProjectError("The ADA Generic internal root dependency must remain pinned")
    return external


def _snapshot(root: Path, project: bytes, runtime: bytes) -> dict:
    return {
        "schema_version": LOCK_SCHEMA,
        "distribution_manifest_sha256": _sha(root / "manifest.json"),
        "wheelhouse_manifest_sha256": _sha(root / "wheelhouse/manifest.json"),
        "external_runtime_sha256": _sha(root / "requirements/external-runtime.txt"),
        "project_sha256": hashlib.sha256(project).hexdigest(),
        "project_runtime_sha256": hashlib.sha256(runtime).hexdigest(),
    }


def _locked(root: Path) -> dict:
    location = root / "requirements"
    lock = location / "project.lock.json"
    runtime = location / "project-runtime.txt"
    if not lock.is_file() or not runtime.is_file():
        raise ProjectError(
            "Project runtime lock is missing; regenerate the distribution or run project lock"
        )
    actual = json.loads(lock.read_text(encoding="utf-8"))
    expected = _snapshot(root, (root / "pyproject.toml").read_bytes(), runtime.read_bytes())
    if actual != expected:
        raise ProjectError(
            "Project runtime lock is stale or the base distribution was modified; run project lock"
        )
    _validate_runtime_requirements(runtime.read_bytes())
    _external_dependencies(root, _read_project(root)[1])
    return actual


def _command(
    args: list[str],
    *,
    root: Path,
    passthrough: bool = False,
    environment: dict[str, str] | None = None,
) -> None:
    try:
        result = subprocess.run(
            args,
            cwd=root,
            env=environment,
            check=False,
            text=True,
            **({} if passthrough else {"capture_output": True}),
        )
    except OSError as error:
        raise ProjectError(f"Required executable is unavailable: {args[0]}") from error
    if result.returncode != 0:
        stderr = "" if passthrough else (result.stderr or "")
        safe = [
            "[diagnostic redacted]"
            if re.search(r"(?i)(://[^/\s]+@|bearer |token[=:]|password[=:]|secret[=:])", line)
            else line
            for line in stderr.splitlines()
        ]
        diagnostic = "\n".join(safe)[-2200:]
        raise ProjectError(
            f"Command failed: {args[0]} ({result.returncode})"
            + (f"\n{diagnostic}" if diagnostic else "")
        )


def _require_uv() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise ProjectError("uv must be installed and available on PATH")
    return executable


# Antes de mutar el entorno local se verifica que la distribución original siga íntegra.
def _check_environment(root: Path) -> None:
    if platform.python_implementation() != "CPython" or platform.python_version() != PYTHON_VERSION:
        raise ProjectError(
            f"Project tooling requires CPython {PYTHON_VERSION}; use project.sh or project.cmd"
        )
    original = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if original.get("profile") != "ada" or original.get("wheelhouse_included") is not True:
        raise ProjectError("A completed ADA distribution is required")
    wheelhouse = json.loads((root / "wheelhouse/manifest.json").read_text(encoding="utf-8"))
    if wheelhouse.get("python") != PYTHON_VERSION:
        raise ProjectError("Internal wheels use a different Python version")
    required = {"external-runtime.txt", "host-runtime.txt", "starter-build.txt"}
    locked = wheelhouse.get("requirements")
    if not isinstance(locked, dict) or set(locked) != required:
        raise ProjectError("Original distribution requirements are incomplete")
    for name, digest in locked.items():
        path = root / "requirements" / name
        if not path.is_file() or _sha(path) != digest:
            raise ProjectError(f"Original distribution requirements were changed: {name}")
    packages = wheelhouse.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ProjectError("Original internal wheels are missing")
    for package in packages:
        filename = package["filename"]
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ProjectError("Original internal wheel identity is invalid")
        path = root / "wheelhouse" / filename
        if not path.is_file() or _sha(path) != package["sha256"]:
            raise ProjectError(f"Original internal wheel was changed: {filename}")
    for name, digest in original.get("files", {}).items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ProjectError("Original source inventory contains an unsafe path")
        if name == "pyproject.toml" or path.parts[0] == "src":
            continue
        file = root / path
        if not file.is_file() or _sha(file) != digest:
            raise ProjectError(f"Original distribution source was changed: {name}")


def _replace_dependencies(text: str, dependencies: list[str]) -> str:
    section = re.search(r"(?m)^\[project\]\s*$", text)
    if section is None:
        raise ProjectError("pyproject.toml does not have a [project] section")
    end_match = re.search(r"(?m)^\[", text[section.end() :])
    end = section.end() + end_match.start() if end_match else len(text)
    body = text[section.end() : end]
    start = re.search(r"(?m)^dependencies\s*=\s*\[", body)
    if start is None:
        raise ProjectError("pyproject.toml does not declare a dependencies array")
    position = start.end()
    quote = False
    escaped = False
    depth = 1
    while position < len(body) and depth:
        char = body[position]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        position += 1
    if depth:
        raise ProjectError("Project dependencies array is unbalanced")
    replacement = (
        "dependencies = [\n"
        + "".join(f"    {json.dumps(item, ensure_ascii=False)},\n" for item in dependencies)
        + "]"
    )
    body = body[: start.start()] + replacement + body[position:]
    return text[: section.end()] + body + text[end:]


def _validate_runtime_requirements(contents: bytes) -> None:
    requirements = 0
    hashed = False
    for raw in contents.decode("utf-8").splitlines():
        value = raw.strip().removesuffix("\\").strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith("--hash="):
            if requirements == 0 or re.fullmatch(r"--hash=sha256:[a-f0-9]{64}", value) is None:
                raise ProjectError("Invalid SHA256 hash in resolved runtime requirements")
            hashed = True
        else:
            if requirements and not hashed:
                raise ProjectError("Unhashed package in resolved runtime requirements")
            if re.match(r"^[A-Za-z0-9_.-]+==[^\s]+", value) is None:
                raise ProjectError("Unsupported requirement in resolved runtime requirements")
            requirements += 1
            hashed = False
    if not requirements or not hashed:
        raise ProjectError("Runtime requirements are empty or unhashed")


def _compile(root: Path, additional: list[str], target: Path, uv: str) -> bytes:
    original = root / "requirements/external-runtime.txt"
    if not additional:
        contents = original.read_bytes()
        _validate_runtime_requirements(contents)
        return contents
    with tempfile.TemporaryDirectory(prefix=".project-resolve-") as temporary:
        extra = Path(temporary) / "additional.in"
        extra.write_text("\n".join(additional) + "\n", encoding="utf-8")
        _command(
            [
                uv,
                "pip",
                "compile",
                str(original),
                str(extra),
                "--constraints",
                str(original),
                "--constraints",
                str(root / "requirements/host-runtime.txt"),
                "--python-version",
                PYTHON_VERSION,
                "--universal",
                "--only-binary",
                ":all:",
                "--generate-hashes",
                "--no-header",
                "--no-annotate",
                "--output-file",
                str(target),
            ],
            root=root,
        )
        if not target.is_file() or not target.stat().st_size:
            raise ProjectError("uv did not produce a project runtime lock")
        contents = target.read_bytes()
        _validate_runtime_requirements(contents)
        return contents


def _save_lock(root: Path, project: bytes, runtime: bytes) -> None:
    requirements = root / "requirements"
    with tempfile.TemporaryDirectory(prefix=".project-write-", dir=requirements) as temporary:
        stage = Path(temporary)
        project_path = stage / "pyproject.toml"
        runtime_path = stage / "project-runtime.txt"
        lock_path = stage / "project.lock.json"
        project_path.write_bytes(project)
        runtime_path.write_bytes(runtime)
        lock_path.write_text(
            json.dumps(_snapshot(root, project, runtime), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        project_path.replace(root / "pyproject.toml")
        runtime_path.replace(requirements / "project-runtime.txt")
        lock_path.replace(requirements / "project.lock.json")
    stamp = root / ".runtime/project-sync.json"
    stamp.unlink(missing_ok=True)


def resolve(root: Path, *, new_dependency: str | None = None) -> dict:
    _check_environment(root)
    uv = _require_uv()
    _, declarations = _read_project(root)
    if new_dependency is not None:
        name = _dependency_name(new_dependency)
        if name in _internal_versions(root):
            raise ProjectError(f"Internal distribution package cannot be changed: {name}")
        declarations = [item for item in declarations if _dependency_name(item) != name]
        declarations.append(new_dependency)
    additional = _external_dependencies(root, declarations)
    original = (root / "pyproject.toml").read_text(encoding="utf-8")
    candidate = (
        _replace_dependencies(original, declarations) if new_dependency is not None else original
    ).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix=".project-lock-", dir=root / "requirements") as temp:
        runtime = _compile(root, additional, Path(temp) / "project-runtime.txt", uv)
    _save_lock(root, candidate, runtime)
    return {"status": "LOCKED", "additional_dependencies": len(additional)}


def _python(root: Path) -> Path:
    executable = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return executable


# Sync crea un entorno reproducible desde requirements con hash, wheels internos y el wheel del host.
def sync(root: Path, *, force: bool = False) -> dict:
    _check_environment(root)
    state = _locked(root)
    uv = _require_uv()
    stamp = root / ".runtime/project-sync.json"
    python = _python(root)
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "lock": state,
                "host_runtime_sha256": _sha(root / "requirements/host-runtime.txt"),
                "python": PYTHON_VERSION,
                "starter_install_schema": 1,
                "starter_source_sha256": _starter_source_digest(root),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if not force and python.is_file() and stamp.is_file():
        try:
            if json.loads(stamp.read_text(encoding="utf-8")).get("fingerprint") == fingerprint:
                return {"status": "ALREADY_SYNCED", "python": str(python)}
        except OSError, ValueError:
            pass
    virtual_environment = root / ".venv"
    if virtual_environment.is_symlink():
        raise ProjectError("Managed virtual environment must not be a symbolic link")
    stamp.unlink(missing_ok=True)
    if virtual_environment.exists():
        shutil.rmtree(virtual_environment)
    _command(
        [uv, "venv", str(virtual_environment), "--python", PYTHON_VERSION, "--no-python-downloads"],
        root=root,
    )
    _command(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--only-binary",
            ":all:",
            "--require-hashes",
            "-r",
            str(root / "requirements/project-runtime.txt"),
            "-r",
            str(root / "requirements/host-runtime.txt"),
        ],
        root=root,
    )
    wheelhouse = root / "wheelhouse"
    wheels = sorted(str(path) for path in wheelhouse.glob("*.whl"))
    if not wheels:
        raise ProjectError("Internal wheelhouse is empty")
    _command(
        [uv, "pip", "install", "--python", str(python), "--no-index", "--no-deps", *wheels],
        root=root,
    )
    with tempfile.TemporaryDirectory(prefix=".ada-starter-build-") as temporary:
        staging = Path(temporary)
        build_environment = staging / "buildvenv"
        build_python = build_environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        output = staging / "wheels"
        output.mkdir()
        _command(
            [
                uv,
                "venv",
                str(build_environment),
                "--python",
                PYTHON_VERSION,
                "--no-python-downloads",
            ],
            root=root,
        )
        _command(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(build_python),
                "--only-binary",
                ":all:",
                "--require-hashes",
                "-r",
                str(root / "requirements/starter-build.txt"),
            ],
            root=root,
        )
        _command(
            [
                uv,
                "build",
                "--wheel",
                "--no-build-isolation",
                "--python",
                str(build_python),
                "--out-dir",
                str(output),
                str(root),
            ],
            root=root,
        )
        starter_wheels = tuple(output.glob("*.whl"))
        if len(starter_wheels) != 1:
            raise ProjectError("ADA Starter build must produce exactly one wheel")
        _command(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                "--no-index",
                "--no-deps",
                str(starter_wheels[0]),
            ],
            root=root,
        )
    _command([uv, "pip", "check", "--python", str(python)], root=root)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps({"fingerprint": fingerprint}, indent=2) + "\n", encoding="utf-8")
    return {"status": "SYNCED", "python": str(python), "internal_wheels": len(wheels)}


def _unresolved_environment(root: Path) -> tuple[str, ...]:
    path = root / ".env"
    if not path.is_file():
        return ()
    unresolved: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*)", line)
        if match is not None and re.search(r"<[^>]+>", match[2]):
            unresolved.append(match[1])
    return tuple(unresolved)


def init(root: Path, *, copy_env: bool = False, no_sync: bool = False) -> dict:
    _check_environment(root)
    try:
        _locked(root)
    except ProjectError:
        lock = root / "requirements/project.lock.json"
        runtime = root / "requirements/project-runtime.txt"
        if lock.exists() or runtime.exists():
            raise
        resolve(root)
    destination = root / ".env"
    copied = False
    if copy_env and not destination.exists():
        shutil.copyfile(root / ".env.detail", destination)
        copied = True
    result = sync(root) if not no_sync else {"status": "LOCKED"}
    result["env_template_copied"] = copied
    result["env_file_present"] = destination.is_file()
    result["env_placeholders"] = _unresolved_environment(root)
    return result


def run(root: Path) -> None:
    if os.environ.get("ATLANTICUS_ENVIRONMENT", "").lower() == "production":
        raise ProjectError("Use Docker and a configured production identity provider in production")
    env_file = root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if re.fullmatch(
                r'\s*ATLANTICUS_ENVIRONMENT\s*=\s*["\']?production["\']?\s*', line, re.I
            ):
                raise ProjectError(
                    "Local run is unavailable when ATLANTICUS_ENVIRONMENT=production"
                )
    unresolved = _unresolved_environment(root)
    if unresolved:
        raise ProjectError(f"Unresolved environment placeholders: {', '.join(unresolved)}")
    sync(root)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            (
                str(root / "src"),
                environment.get("PYTHONPATH", ""),
            ),
        )
    )
    _command(
        [str(_python(root)), "-m", "application"],
        root=root,
        passthrough=True,
        environment=environment,
    )


def docker(root: Path, action: str, *, tag: str | None = None) -> None:
    _check_environment(root)
    _locked(root)
    name = tag or "ada-generic:local"
    if action == "build":
        _command(["docker", "build", "--tag", name, str(root)], root=root, passthrough=True)
        return
    if action == "run":
        unresolved = _unresolved_environment(root)
        if unresolved:
            raise ProjectError(f"Unresolved environment placeholders: {', '.join(unresolved)}")
        command = ["docker", "run", "--rm", "--publish", "8000:8000"]
        if (root / ".env").is_file():
            command.extend(("--env-file", str(root / ".env")))
        _command([*command, name], root=root, passthrough=True)
        return
    raise ProjectError(f"Unsupported Docker operation: {action}")


def _compose_setting(root: Path, key: str, default: str = "") -> str:
    parent = os.environ.get(key)
    if parent is not None:
        return parent
    location = root / ".env"
    if not location.is_file():
        return default
    for line in location.read_text(encoding="utf-8").splitlines():
        if re.fullmatch(rf"{re.escape(key)}\s*=.*", line.strip()):
            raw = line.split("=", 1)[1].strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
                raw = raw[1:-1]
            return raw
    return default


def _docker_network(root: Path, *, create: bool) -> None:
    name = _compose_setting(root, "ADA_COMPOSE_NETWORK", _COMPOSE_NETWORK_DEFAULT)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", name) is None:
        raise ProjectError("ADA_COMPOSE_NETWORK is not a valid Docker network name")
    result = subprocess.run(
        ["docker", "network", "inspect", name],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    if not create:
        raise ProjectError("The supporting network is missing; start infra or full first")
    _command(["docker", "network", "create", "--driver", "bridge", name], root=root)


def _docker_volumes(root: Path) -> None:
    for key, default in (
        ("ADA_COSMOS_VOLUME", "ada-generic-cosmos"),
        ("ADA_AZURITE_VOLUME", "ada-generic-azurite"),
    ):
        name = _compose_setting(root, key, default)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", name) is None:
            raise ProjectError(f"{key} is not a valid Docker volume name")
        _command(["docker", "volume", "create", name], root=root)


def _running_compose_project(root: Path, project: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProjectError("Could not inspect running Docker Compose projects")
    return bool(result.stdout.strip())


def _validate_compose_start(root: Path, profile: str) -> None:
    if profile != "infra" and not (root / ".env").is_file():
        raise ProjectError("The selected Compose profile requires a configured .env file")
    if profile == "full":
        namespace = _compose_setting(root, "ADA_TOOL_NAMESPACE")
        if not namespace or re.search(r"<[^>]+>", namespace):
            raise ProjectError("Set ADA_TOOL_NAMESPACE in .env before starting full Compose")
    if profile == "web":
        values = {
            key: _compose_setting(root, key)
            for key in (
                "ADA_MANAGER_PERSISTENCE_PROVIDER",
                "ADA_TOOL_SOURCE_PROVIDER",
                "ADA_TOOL_PROJECTION_PROVIDER",
            )
        }
        if values != {
            "ADA_MANAGER_PERSISTENCE_PROVIDER": "durable",
            "ADA_TOOL_SOURCE_PROVIDER": "blob",
            "ADA_TOOL_PROJECTION_PROVIDER": "cosmos",
        }:
            raise ProjectError(
                "Web Compose requires durable Manager, Blob Source and Cosmos Projection"
            )
        unresolved = _unresolved_environment(root)
        if unresolved:
            raise ProjectError(f"Unresolved environment placeholders: {', '.join(unresolved)}")


def compose(root: Path, action: str, profile: str) -> None:
    if action not in COMPOSE_ACTIONS or profile not in COMPOSE_PROFILES:
        raise ProjectError("Unsupported Compose operation or profile")
    location = root / "deployment/compose" / f"{profile}.yaml"
    if location.is_symlink() or not location.is_file():
        raise ProjectError(f"Compose profile is not generated yet: {profile}")
    if action in ("up", "prepare"):
        if action == "prepare" and profile != "web":
            raise ProjectError("Local resource preparation is available only for web Compose")
        _validate_compose_start(root, profile)
        if profile in ("infra", "full"):
            incompatible = ("full",) if profile == "infra" else ("infra", "web")
            if any(
                _running_compose_project(root, _COMPOSE_PROJECTS[item]) for item in incompatible
            ):
                raise ProjectError(
                    "Stop incompatible infra/full/web Compose stacks before switching"
                )
        _docker_network(root, create=True)
        if action == "up" and profile in ("infra", "full"):
            _docker_volumes(root)
    if action == "prepare":
        _command(
            [
                "docker",
                "compose",
                "--project-directory",
                str(root),
                "-f",
                str(location),
                "--profile",
                "setup",
                "run",
                "--rm",
                "--no-deps",
                "resources",
            ],
            root=root,
            passthrough=True,
        )
        return
    arguments = {
        "up": ["up", "--detach"],
        "down": ["down"],
        "logs": ["logs", "--follow"],
        "ps": ["ps"],
        "build": ["build"],
    }[action]
    _command(
        ["docker", "compose", "--project-directory", str(root), "-f", str(location), *arguments],
        root=root,
        passthrough=True,
    )


# El bootstrap del proyecto entrega explícitamente su root; este paquete no depende de su ubicación física.
def main(argv: list[str] | None = None, *, root: Path) -> None:
    parser = argparse.ArgumentParser(description="Manage a distributed ADA Web project")
    sub = parser.add_subparsers(dest="operation", required=True)
    initialization = sub.add_parser("init")
    initialization.add_argument("--copy-env", action="store_true")
    initialization.add_argument("--no-sync", action="store_true")
    dependencies = sub.add_parser("add")
    dependencies.add_argument("dependency")
    sub.add_parser("lock")
    installation = sub.add_parser("sync")
    installation.add_argument("--force", action="store_true")
    sub.add_parser("run")
    container = sub.add_parser("docker")
    container.add_argument("action", choices=("build", "run"))
    container.add_argument("--tag")
    orchestration = sub.add_parser("compose")
    orchestration.add_argument("action", choices=sorted(COMPOSE_ACTIONS))
    orchestration.add_argument("profile", choices=sorted(COMPOSE_PROFILES))
    args = parser.parse_args(argv)
    try:
        if args.operation == "init":
            result = init(root, copy_env=args.copy_env, no_sync=args.no_sync)
        elif args.operation == "add":
            result = resolve(root, new_dependency=args.dependency)
        elif args.operation == "lock":
            result = resolve(root)
        elif args.operation == "sync":
            result = sync(root, force=args.force)
        elif args.operation == "run":
            run(root)
            result = {"status": "STOPPED"}
        elif args.operation == "docker":
            docker(root, args.action, tag=args.tag)
            result = {"status": "COMPLETED"}
        else:
            compose(root, args.action, args.profile)
            result = {"status": "COMPLETED"}
    except (ProjectError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            json.dumps({"status": "BLOCKED", "error": str(error)}, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        raise SystemExit(2) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))
