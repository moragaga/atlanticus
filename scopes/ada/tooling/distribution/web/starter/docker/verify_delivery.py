from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path


class DeliveryValidationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_delivery(application: Path) -> int:
    starter = json.loads((application / "manifest.json").read_text(encoding="utf-8"))
    wheelhouse = application / "wheelhouse"
    manifest = json.loads((wheelhouse / "manifest.json").read_text(encoding="utf-8"))
    strategy = "internal-wheels-external-image-build"
    if (
        starter.get("artifact_kind") != "web-application-starter"
        or starter.get("profile") != "ada"
        or starter.get("wheelhouse_included") is not True
        or starter.get("delivery_strategy") != strategy
    ):
        raise DeliveryValidationError("ADA Starter manifest has an invalid delivery contract")
    if (
        manifest.get("schema_version") != 2
        or manifest.get("strategy") != strategy
        or manifest.get("profile") != "ada"
        or manifest.get("python") != platform.python_version()
    ):
        raise DeliveryValidationError("ADA distribution contract or image Python differs")
    requirements = manifest.get("requirements")
    required = {"external-runtime.txt", "host-runtime.txt", "starter-build.txt"}
    if not isinstance(requirements, dict) or set(requirements) != required:
        raise DeliveryValidationError("ADA external requirements inventory is incomplete")
    for name, digest in requirements.items():
        path = application / "requirements" / name
        if not path.is_file() or _sha256(path) != digest:
            raise DeliveryValidationError(f"ADA requirements integrity failed: {name}")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise DeliveryValidationError("ADA internal wheel inventory is empty")
    expected: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise DeliveryValidationError("ADA internal wheel record is invalid")
        name, digest = package.get("filename"), package.get("sha256")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.endswith(".whl")
            or name in expected
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise DeliveryValidationError("ADA internal wheel identity is invalid")
        expected.add(name)
        path = wheelhouse / name
        if not path.is_file() or _sha256(path) != digest:
            raise DeliveryValidationError(f"ADA internal wheel integrity failed: {name}")
    if {path.name for path in wheelhouse.glob("*.whl")} != expected:
        raise DeliveryValidationError("ADA internal wheel inventory differs from its manifest")
    project_runtime = application / "requirements/project-runtime.txt"
    project_lock = application / "requirements/project.lock.json"
    if not project_runtime.is_file() or not project_lock.is_file():
        raise DeliveryValidationError("Project runtime lock is missing or incomplete")
    try:
        lock = json.loads(project_lock.read_text(encoding="utf-8"))
        expected_lock = {
            "schema_version": 1,
            "distribution_manifest_sha256": _sha256(application / "manifest.json"),
            "wheelhouse_manifest_sha256": _sha256(wheelhouse / "manifest.json"),
            "external_runtime_sha256": _sha256(application / "requirements/external-runtime.txt"),
            "project_sha256": _sha256(application / "pyproject.toml"),
            "project_runtime_sha256": _sha256(project_runtime),
        }
    except (OSError, ValueError) as error:
        raise DeliveryValidationError("Project runtime lock is unreadable") from error
    if lock != expected_lock:
        raise DeliveryValidationError("Project runtime lock integrity failed")
    return len(packages)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_delivery.py <application-root>")
    try:
        verify_delivery(Path(sys.argv[1]))
    except (DeliveryValidationError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
