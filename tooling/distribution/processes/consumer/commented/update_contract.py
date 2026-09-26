from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Mapping

REQUIRED_FILES = ("pyproject.toml", "uv.lock")
REQUIRED_DIRECTORIES = ("wheels",)
MAX_FILES = 10000
MAX_BYTES = 2_000_000_000
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ALIAS_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# Error de contrato: archivos permitidos e invariantes de dependencias.
class UpdateContractError(ValueError):
    pass


def is_dependency_file(name: str) -> bool:
    return name in REQUIRED_FILES or (
        name.startswith("wheels/")
        and name.count("/") == 1
        and name.endswith(".whl")
        and Path(name).name == name.removeprefix("wheels/")
    )


def hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fingerprint(files: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for relative, sha256 in sorted(files.items()):
        if not is_dependency_file(relative) or not SHA256_PATTERN.fullmatch(sha256):
            raise UpdateContractError(
                f"Invalid dependency fingerprint entry: {relative}"
            )
        digest.update(json.dumps([relative, sha256], separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def validate_dependencies(files: Mapping[str, str], directories: set[str]) -> None:
    if len(files) > MAX_FILES or any(name not in files for name in REQUIRED_FILES):
        raise UpdateContractError("Dependency transport is incomplete or too large")
    if directories != {"wheels"} or any(not is_dependency_file(name) for name in files):
        raise UpdateContractError("Dependency transport contains unexpected entries")
    fingerprint(files)
    wheel_versions(files)


# El inventario ignora por contrato el código y el estado particular del consumidor.
def inventory(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise UpdateContractError(f"Invalid process root: {root}")
    files: dict[str, str] = {}
    total = 0
    for name in REQUIRED_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise UpdateContractError(f"Missing or unsafe dependency file: {path}")
        total += path.stat().st_size
        files[name] = hash_content(path.read_bytes())
    directory = root / "wheels"
    if directory.is_symlink() or not directory.is_dir():
        raise UpdateContractError(f"Missing or unsafe wheels directory: {directory}")
    for path in sorted(directory.iterdir()):
        if (
            path.is_symlink()
            or not path.is_file()
            or not is_dependency_file(f"wheels/{path.name}")
        ):
            raise UpdateContractError(f"Unexpected wheel entry: {path}")
        total += path.stat().st_size
        files[f"wheels/{path.name}"] = hash_content(path.read_bytes())
        if total > MAX_BYTES or len(files) > MAX_FILES:
            raise UpdateContractError("Dependency transport exceeds size limits")
    validate_dependencies(files, {"wheels"})
    return files


def wheel_versions(files: Mapping[str, str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in files:
        if not name.startswith("wheels/"):
            continue
        filename = Path(name).name
        parts = filename.removesuffix(".whl").split("-")
        if not filename.endswith(".whl") or len(parts) not in (5, 6):
            raise UpdateContractError(f"Invalid wheel filename: {name}")
        package = re.sub(r"[-_.]+", "-", parts[0]).lower()
        if package in versions:
            raise UpdateContractError(f"Multiple versions of the same wheel: {package}")
        versions[package] = parts[1]
    return versions


# Impide que una actualización cambie el contenido de un wheel sin cambiar su versión.
def changed_wheels(
    previous: Mapping[str, str], current: Mapping[str, str]
) -> list[dict[str, str | None]]:
    before, after = wheel_versions(previous), wheel_versions(current)
    for package, version in before.items():
        if after.get(package) == version:
            old = next(
                (
                    digest
                    for name, digest in previous.items()
                    if name.startswith("wheels/")
                    and re.sub(r"[-_.]+", "-", Path(name).name.split("-")[0]).lower()
                    == package
                ),
                None,
            )
            new = next(
                (
                    digest
                    for name, digest in current.items()
                    if name.startswith("wheels/")
                    and re.sub(r"[-_.]+", "-", Path(name).name.split("-")[0]).lower()
                    == package
                ),
                None,
            )
            if old != new:
                raise UpdateContractError(
                    f"Wheel version content changed without a version bump: {package}=={version}"
                )
    return [
        {"name": name, "from": before.get(name), "to": after.get(name)}
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    ]


# Normaliza sólo los campos de dependencias permitidos por este incremento.
def _project_without_dependency_changes(content: bytes) -> dict:
    try:
        project = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise UpdateContractError("Process pyproject.toml is invalid") from error
    if not isinstance(project.get("project"), dict):
        raise UpdateContractError("Process metadata is missing")
    project["project"].pop("dependencies", None)
    groups = project.get("dependency-groups", {})
    if not isinstance(groups, dict):
        raise UpdateContractError("Dependency groups are invalid")
    groups.pop("bundle-internal", None)
    tool = project.get("tool", {})
    if not isinstance(tool, dict):
        raise UpdateContractError("Tool metadata is invalid")
    uv = tool.get("uv", {})
    if not isinstance(uv, dict):
        raise UpdateContractError("UV metadata is invalid")
    uv.pop("sources", None)
    return project


# Permite modificar dependencias sin alterar identidad ni contratos del proceso.
def validate_pyproject_change(before: bytes, after: bytes) -> None:
    if _project_without_dependency_changes(
        before
    ) != _project_without_dependency_changes(after):
        raise UpdateContractError(
            "Non-dependency process metadata changed; a dependency update cannot change process code contracts"
        )
    target = tomllib.loads(after.decode("utf-8"))
    sources = target.get("tool", {}).get("uv", {}).get("sources", {})
    if not isinstance(sources, dict):
        raise UpdateContractError("UV dependency source mapping is invalid")
    for key, item in sources.items():
        if (
            not isinstance(key, str)
            or not isinstance(item, dict)
            or set(item) != {"path"}
            or not isinstance(item["path"], str)
            or not is_dependency_file(item["path"])
            or not item["path"].startswith("wheels/")
        ):
            raise UpdateContractError("Update has a non-transport dependency source")
