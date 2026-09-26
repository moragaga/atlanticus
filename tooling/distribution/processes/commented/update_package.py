from __future__ import annotations

import json
import re
import tempfile
import zipfile
from pathlib import Path
from types import ModuleType

from consumer.update_contract import (
    UpdateContractError,
    changed_wheels,
    fingerprint,
    hash_content,
    inventory,
    is_dependency_file,
    validate_dependencies,
    validate_pyproject_change,
)


# Error de frontera para rechazar paquetes de actualización incompatibles.
class ProcessUpdateError(RuntimeError):
    pass


# Usa una distribución de referencia para fijar el estado anterior de las dependencias.
def _baseline(root: Path, distribution: str, command: str) -> tuple[dict, dict, Path]:
    try:
        manifest = json.loads((root / "distribution.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProcessUpdateError(
            "Baseline distribution manifest is unreadable"
        ) from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("name") != distribution
    ):
        raise ProcessUpdateError("Baseline distribution identity does not match")
    matches = [
        entry
        for entry in manifest.get("processes", [])
        if isinstance(entry, dict) and entry.get("process") == command
    ]
    if len(matches) != 1:
        raise ProcessUpdateError(f"Baseline process is missing or ambiguous: {command}")
    entry = matches[0]
    deployment = entry.get("deployment")
    alias = deployment.get("execution_file") if isinstance(deployment, dict) else None
    if not isinstance(alias, str) or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", alias
    ):
        raise ProcessUpdateError("Baseline process alias is invalid")
    path = root / "processes" / alias
    if path.is_symlink() or (root / "processes").is_symlink():
        raise ProcessUpdateError("Baseline process path is unsafe")
    return manifest, entry, path


# Crea el ZIP desde un artifact nuevo, pero transporta únicamente dependencias.
def create_update(
    *,
    builder: ModuleType,
    repository_root: Path,
    baseline_root: Path,
    distribution_name: str,
    process: str,
    output_root: Path,
) -> Path:
    baseline_root = baseline_root.resolve()
    _, previous, previous_root = _baseline(baseline_root, distribution_name, process)
    try:
        previous_files = inventory(previous_root)
        previous_project = (previous_root / "pyproject.toml").read_bytes()
    except (OSError, UpdateContractError) as error:
        raise ProcessUpdateError(
            f"Baseline dependency files are invalid: {error}"
        ) from error
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atlanticus-dependencies-") as temporary:
        temp = Path(temporary)
        # Reutiliza el builder actual para obtener un lock y wheels consistentes.
        extension_path = builder.distribute(
            repository_root=repository_root,
            output_root=temp,
            distribution_name=distribution_name,
            selections=(process,),
            targets=(),
            extension=True,
        )
        with zipfile.ZipFile(extension_path) as extension:
            if extension.testzip() is not None:
                raise ProcessUpdateError("Generated extension ZIP is corrupt")
            generated = json.loads(extension.read("extension.json"))
            selected = generated["processes"]
            if len(selected) != 1:
                raise ProcessUpdateError(
                    "A dependency update requires exactly one process"
                )
            target = selected[0]
            if (
                target["process"] != previous["process"]
                or target["project"] != previous["project"]
                or target["version"] != previous["version"]
                or target["deployment"] != previous["deployment"]
                or target["runtime"] != previous["runtime"]
            ):
                raise ProcessUpdateError(
                    "Process identity, code version, deployment or runtime changed"
                )
            alias = previous["deployment"]["execution_file"]
            prefix = f"processes/{alias}/"
            payload: dict[str, bytes] = {}
            directories: set[str] = set()
            # Se ignoran deliberadamente src y las plantillas: el ZIP sólo contiene dependencias.
            for item in extension.infolist():
                name = item.filename
                if name in {"extension.json", "processes/", f"processes/{alias}/"}:
                    continue
                if not name.startswith(prefix):
                    raise ProcessUpdateError(
                        f"Unexpected generated extension entry: {name}"
                    )
                relative = name[len(prefix) :]
                if item.is_dir():
                    if relative == "wheels/":
                        directories.add("wheels")
                    continue
                if is_dependency_file(relative):
                    if relative in payload:
                        raise ProcessUpdateError(
                            f"Duplicate dependency file: {relative}"
                        )
                    payload[relative] = extension.read(item)
            target_hashes = {name: hash_content(data) for name, data in payload.items()}
            try:
                validate_dependencies(target_hashes, directories)
                validate_pyproject_change(previous_project, payload["pyproject.toml"])
                changes = changed_wheels(previous_files, target_hashes)
            except UpdateContractError as error:
                raise ProcessUpdateError(str(error)) from error
            # No se generan paquetes vacíos ni se permite republicar un mismo wheel alterado.
            if fingerprint(previous_files) == fingerprint(target_hashes):
                raise ProcessUpdateError("No dependency changes were found")
            manifest = {
                "schema_version": 1,
                "kind": "dependency-update",
                "distribution": distribution_name,
                "source": generated["source"],
                "process": {
                    "alias": alias,
                    "command": previous["process"],
                    "project": previous["project"],
                    "version": previous["version"],
                    "deployment": previous["deployment"],
                    "runtime": previous["runtime"],
                },
                "from": {"fingerprint": fingerprint(previous_files)},
                "to": {"fingerprint": fingerprint(target_hashes)},
                "changed_wheels": changes,
                "payload": {
                    f"{prefix}{name}": digest
                    for name, digest in sorted(target_hashes.items())
                },
            }
            name = f"{distribution_name}.{alias}.dependencies-{fingerprint(target_hashes)[:12]}.zip"
            target_path = output_root / name
            if target_path.exists():
                raise ProcessUpdateError(
                    f"Dependency update ZIP already exists: {target_path}"
                )
            pending = temp / name
            with zipfile.ZipFile(
                pending, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("update.json", json.dumps(manifest, indent=2) + "\n")
                archive.writestr("processes/", b"")
                archive.writestr(f"processes/{alias}/", b"")
                archive.writestr(f"{prefix}wheels/", b"")
                for relative, data in sorted(payload.items()):
                    archive.writestr(f"{prefix}{relative}", data)
            pending.replace(target_path)
            return target_path
