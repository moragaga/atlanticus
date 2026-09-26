from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tomllib
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from update_contract import (
    ALIAS_PATTERN,
    MAX_BYTES,
    MAX_FILES,
    SHA256_PATTERN,
    UpdateContractError,
    changed_wheels,
    fingerprint,
    hash_content,
    inventory,
    validate_dependencies,
    validate_pyproject_change,
    wheel_versions,
)


class ProcessUpdateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    alias: str
    manifest: dict
    payload: dict[str, str]


def _load_archive(archive: zipfile.ZipFile) -> tuple[dict, dict[str, str], set[str]]:
    entries: dict[str, str] = {}
    directories: set[str] = set()
    seen: set[str] = set()
    total = 0
    if len(archive.infolist()) > MAX_FILES + 5:
        raise ProcessUpdateError("Dependency ZIP has too many entries")
    for item in archive.infolist():
        name = item.filename
        parts = name.rstrip("/").split("/")
        mode = (item.external_attr >> 16) & 0xFFFF
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or any(part in {"", ".", ".."} for part in parts)
            or name.rstrip("/") in seen
            or stat.S_ISLNK(mode)
        ):
            raise ProcessUpdateError(f"Unsafe dependency ZIP entry: {name}")
        seen.add(name.rstrip("/"))
        if item.is_dir():
            directories.add(name)
            continue
        total += item.file_size
        if total > MAX_BYTES:
            raise ProcessUpdateError("Dependency ZIP exceeds size limit")
        if name != "update.json":
            entries[name] = hash_content(archive.read(item))
    if "update.json" not in seen or "update.json" in directories:
        raise ProcessUpdateError("Dependency update manifest is missing")
    try:
        manifest = json.loads(archive.read("update.json"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ProcessUpdateError("Dependency update manifest is invalid") from error
    return manifest, entries, directories


def _validate_sources(project_bytes: bytes, files: dict[str, str]) -> None:
    project = tomllib.loads(project_bytes.decode("utf-8"))
    sources = project.get("tool", {}).get("uv", {}).get("sources", {})
    paths = set()
    wheel_names = wheel_versions(files)
    for name, value in sources.items():
        path = value["path"]
        filename = Path(path).name
        identity = re.sub(r"[-_.]+", "-", filename.split("-")[0]).lower()
        canonical = re.sub(r"[-_.]+", "-", name).lower()
        if path not in files or identity != canonical or canonical not in wheel_names:
            raise ProcessUpdateError(
                f"UV source does not match an included wheel: {name}"
            )
        paths.add(path)
    if paths != {name for name in files if name.startswith("wheels/")}:
        raise ProcessUpdateError("Included wheels disagree with UV source mapping")


def inspect_update(root: Path, archive_path: Path, consumer: ModuleType) -> UpdatePlan:
    consumer._validate_distribution(root, require_environment=False)
    installed_manifest = consumer._manifest(root)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            manifest, entries, directories = _load_archive(archive)
            if archive.testzip() is not None:
                raise ProcessUpdateError("Dependency ZIP checksum validation failed")
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != 1
                or manifest.get("kind") != "dependency-update"
                or manifest.get("distribution") != installed_manifest["name"]
            ):
                raise ProcessUpdateError(
                    "Unsupported or mismatched dependency update manifest"
                )
            source = manifest.get("source")
            identity = manifest.get("process")
            before = manifest.get("from")
            after = manifest.get("to")
            if not all(
                isinstance(item, dict) for item in (source, identity, before, after)
            ):
                raise ProcessUpdateError("Dependency update identity is invalid")
            if source.get("repository") != "atlanticus" or not re.fullmatch(
                r"[a-f0-9]{40}", str(source.get("revision", ""))
            ):
                raise ProcessUpdateError("Dependency update source revision is invalid")
            alias = identity.get("alias")
            if not isinstance(alias, str) or not ALIAS_PATTERN.fullmatch(alias):
                raise ProcessUpdateError("Dependency update process alias is invalid")
            matching = [
                item
                for item in installed_manifest["processes"]
                if item["deployment"]["execution_file"] == alias
            ]
            if len(matching) != 1:
                raise ProcessUpdateError(
                    "Dependency update process is absent or ambiguous"
                )
            active = matching[0]
            if (
                identity.get("command") != active["process"]
                or identity.get("project") != active["project"]
                or identity.get("version") != active["version"]
                or identity.get("deployment") != active["deployment"]
                or identity.get("runtime") != active["runtime"]
            ):
                raise ProcessUpdateError(
                    "Dependency update targets a different process identity"
                )
            for value in (before, after):
                if not isinstance(
                    value.get("fingerprint"), str
                ) or not SHA256_PATTERN.fullmatch(value["fingerprint"]):
                    raise ProcessUpdateError("Dependency update fingerprint is invalid")
            prefix = f"processes/{alias}/"
            expected_dirs = {"processes/", f"processes/{alias}/", f"{prefix}wheels/"}
            if directories != expected_dirs or any(
                not name.startswith(prefix) for name in entries
            ):
                raise ProcessUpdateError(
                    "Dependency ZIP contains unexpected directories or process files"
                )
            files = {name[len(prefix) :]: digest for name, digest in entries.items()}
            validate_dependencies(files, {"wheels"})
            if (
                not isinstance(manifest.get("payload"), dict)
                or manifest["payload"] != entries
            ):
                raise ProcessUpdateError(
                    "Dependency ZIP integrity does not match manifest"
                )
            if fingerprint(files) != after["fingerprint"]:
                raise ProcessUpdateError("Dependency ZIP target fingerprint is invalid")
            process_root = root / "processes" / alias
            current_files = inventory(process_root)
            if fingerprint(current_files) != before["fingerprint"]:
                raise ProcessUpdateError(
                    "Installed dependencies differ from the requested baseline"
                )
            baseline_project = (process_root / "pyproject.toml").read_bytes()
            target_project = archive.read(f"{prefix}pyproject.toml")
            validate_pyproject_change(baseline_project, target_project)
            for project_bytes in (baseline_project, target_project):
                project_meta = tomllib.loads(project_bytes.decode("utf-8"))["project"]
                if (
                    project_meta.get("name") != active["project"]
                    or project_meta.get("version") != active["version"]
                ):
                    raise ProcessUpdateError(
                        "Process pyproject identity disagrees with distribution manifest"
                    )
            _validate_sources(archive.read(f"{prefix}pyproject.toml"), files)
            tomllib.loads(archive.read(f"{prefix}uv.lock").decode("utf-8"))
            if changed_wheels(current_files, files) != manifest.get("changed_wheels"):
                raise ProcessUpdateError(
                    "Declared wheel changes do not match dependency ZIP"
                )
            if before["fingerprint"] == after["fingerprint"]:
                raise ProcessUpdateError("Dependency update has no changes")
            return UpdatePlan(alias=alias, manifest=manifest, payload=entries)
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
        UnicodeDecodeError,
        UpdateContractError,
    ) as error:
        if isinstance(error, ProcessUpdateError):
            raise
        raise ProcessUpdateError(
            f"Invalid dependency update or installed process: {error}"
        ) from error


def apply_update(root: Path, archive_path: Path, consumer: ModuleType) -> Path:
    updates = root / ".updates"
    if updates.is_symlink() or (root / "processes").is_symlink():
        raise ProcessUpdateError("Unsafe update root")
    updates.mkdir(mode=0o700, exist_ok=True)
    lock = updates / ".lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ProcessUpdateError("Another dependency update is in progress") from error
    try:
        os.close(descriptor)
        plan = inspect_update(root, archive_path, consumer)
        alias = plan.alias
        process_root = root / "processes" / alias
        history = updates / alias
        if process_root.is_symlink() or history.is_symlink():
            raise ProcessUpdateError("Unsafe process update destination")
        history.mkdir(mode=0o700, exist_ok=True)
        if process_root.stat().st_dev != history.stat().st_dev:
            raise ProcessUpdateError(
                "Dependency update requires staging and backup on the same filesystem"
            )
        transaction = uuid.uuid4().hex
        backup = history / transaction
        backup.mkdir(mode=0o700)
        stage = process_root / f".dependencies-stage-{transaction}"
        transfers: list[tuple[str, bool, bool]] = []
        success = False
        restored = False
        try:
            stage.mkdir()
            (stage / "wheels").mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                for name, digest in plan.payload.items():
                    relative = name.removeprefix(f"processes/{alias}/")
                    data = archive.read(name)
                    if hash_content(data) != digest:
                        raise ProcessUpdateError(
                            f"Dependency update changed during staging: {name}"
                        )
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            if fingerprint(inventory(stage)) != plan.manifest["to"]["fingerprint"]:
                raise ProcessUpdateError(
                    "Staged dependencies differ from the update manifest"
                )
            if (
                fingerprint(inventory(process_root))
                != plan.manifest["from"]["fingerprint"]
            ):
                raise ProcessUpdateError(
                    "Installed dependencies changed during staging"
                )
            previous = backup / "previous"
            previous.mkdir()
            for name in ("pyproject.toml", "uv.lock", "wheels"):
                original = process_root / name
                preserved = previous / name
                os.replace(original, preserved)
                transfers.append((name, True, False))
                os.replace(stage / name, original)
                transfers[-1] = (name, True, True)
            if (
                fingerprint(inventory(process_root))
                != plan.manifest["to"]["fingerprint"]
            ):
                raise ProcessUpdateError(
                    "Applied dependencies did not match the requested update"
                )
            consumer._validate_distribution(root, require_environment=False)
            (backup / "applied.json").write_text(
                json.dumps(
                    {
                        "status": "STAGED",
                        "kind": "dependency-update",
                        "process": alias,
                        "from": plan.manifest["from"],
                        "to": plan.manifest["to"],
                        "source": plan.manifest["source"],
                        "changed_wheels": plan.manifest["changed_wheels"],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            success = True
            return backup
        except BaseException:
            for name, moved_old, installed_new in reversed(transfers):
                if installed_new:
                    current = process_root / name
                    if current.is_dir():
                        shutil.rmtree(current)
                    else:
                        current.unlink()
                if moved_old:
                    os.replace(backup / "previous" / name, process_root / name)
            restored = True
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
            if not success and restored:
                shutil.rmtree(backup, ignore_errors=True)
    finally:
        lock.unlink(missing_ok=True)
