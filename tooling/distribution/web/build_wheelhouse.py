from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

WEB_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = WEB_ROOT.parents[2]
PYTHON_VERSION = "3.14.2"
_PRODUCTS = tomllib.loads((WEB_ROOT / "products.toml").read_text(encoding="utf-8"))[
    "products"
]
_PROFILES = tuple(_PRODUCTS)


class WheelhouseBuildError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise WheelhouseBuildError(
            f"uv {command[1]} failed (exit {result.returncode}); inspect uv diagnostics locally"
        )


def _require_python() -> None:
    if (
        platform.python_implementation() != "CPython"
        or platform.python_version() != PYTHON_VERSION
    ):
        raise WheelhouseBuildError(f"Build requires CPython {PYTHON_VERSION}")


def _validate_starter(application: Path, profile: str) -> dict:
    path = application / "manifest.json"
    if not path.is_file():
        raise WheelhouseBuildError("Starter manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("artifact_kind") != "web-application-starter"
        or manifest.get("profile") != profile
    ):
        raise WheelhouseBuildError("Starter artifact kind or profile is invalid")
    if manifest.get("wheelhouse_included") is not False:
        raise WheelhouseBuildError(
            "Starter must be regenerated before building the wheelhouse"
        )
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not entries:
        raise WheelhouseBuildError("Starter manifest has no valid file inventory")
    for relative, digest in entries.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not isinstance(digest, str):
            raise WheelhouseBuildError("Starter manifest contains an invalid file")
        file = application / path
        if not file.is_file() or _sha256(file) != digest:
            raise WheelhouseBuildError(
                f"Starter file differs from manifest: {relative}"
            )
    metadata = _read_toml(application / "pyproject.toml")
    if PYTHON_VERSION not in SpecifierSet(metadata["project"]["requires-python"]):
        raise WheelhouseBuildError(
            "Starter Python requirement differs from current runtime"
        )
    return manifest


def _export_runtime_lock(
    uv: str, project: Path, package: str | None, destination: Path
) -> dict:
    command = [
        uv,
        "export",
        "--project",
        str(project),
        "--locked",
        "--no-dev",
        "--no-default-groups",
        "--format",
        "pylock.toml",
        "--output-file",
        str(destination),
    ]
    if package is not None:
        command.extend(("--package", package))
    _run(command, cwd=project)
    result = _read_toml(destination)
    if result.get("lock-version") != "1.0" or not isinstance(
        result.get("packages"), list
    ):
        raise WheelhouseBuildError("uv did not export a supported runtime pylock")
    return result


def _active_packages(lock: dict) -> list[dict]:
    selected: list[dict] = []
    seen: dict[str, str] = {}
    for package in lock["packages"]:
        marker = package.get("marker")
        if marker is not None:
            if "extra" in marker:
                raise WheelhouseBuildError("pylock retains unresolved extra markers")
            if not Marker(marker).evaluate():
                continue
        name = canonicalize_name(package["name"])
        version = package.get("version", "<local>")
        if name in seen:
            raise WheelhouseBuildError(
                f"Ambiguous runtime dependency in exported lock: {name}"
            )
        seen[name] = version
        selected.append(package)
    return selected


def _local_directory(package: dict, project: Path, root: Path) -> Path:
    source = package["directory"]
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise WheelhouseBuildError("Locked local package has no directory path")
    path = (project / source["path"]).resolve()
    if (
        not path.is_relative_to(root.resolve())
        or not (path / "pyproject.toml").is_file()
    ):
        raise WheelhouseBuildError(
            f"Locked local package is outside repository: {package['name']}"
        )
    metadata = _read_toml(path / "pyproject.toml")["project"]
    if canonicalize_name(metadata["name"]) != canonicalize_name(package["name"]):
        raise WheelhouseBuildError(
            f"Locked local package name mismatch: {package['name']}"
        )
    if package.get("version") is not None and str(metadata["version"]) != str(
        package["version"]
    ):
        raise WheelhouseBuildError(
            f"Locked local package version mismatch: {package['name']}"
        )
    if PYTHON_VERSION not in SpecifierSet(metadata["requires-python"]):
        raise WheelhouseBuildError(
            f"Locked local package requires another Python: {package['name']}"
        )
    return path


def _choose_wheel(
    package: dict, compatibility: dict
) -> tuple[str, str, str, int | None]:
    name = canonicalize_name(package["name"])
    candidates = []
    for artifact in package.get("wheels", []):
        url = artifact.get("url", "")
        filename = artifact.get("name") or urllib.parse.unquote(
            urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        )
        if not filename or Path(filename).name != filename:
            continue
        try:
            wheel_name, wheel_version, _, tags = parse_wheel_filename(filename)
        except ValueError:
            continue
        if wheel_name != name or str(wheel_version) != str(package["version"]):
            continue
        ranks = [compatibility[tag] for tag in tags if tag in compatibility]
        if not ranks:
            continue
        hashes = artifact.get("hashes", {})
        sha = hashes.get("sha256") if isinstance(hashes, dict) else None
        if not isinstance(sha, str) or len(sha) != 64:
            continue
        candidates.append((min(ranks), filename, url, sha, artifact.get("size")))
    if not candidates:
        raise WheelhouseBuildError(
            f"No SHA256-locked compatible wheel: {name}=={package['version']}"
        )
    _, filename, url, sha, size = min(candidates)
    if urllib.parse.urlsplit(url).scheme not in ("https", "file"):
        raise WheelhouseBuildError(
            f"Locked wheel uses an unsupported URL scheme: {name}"
        )
    return filename, url, sha, size


def _choose_sdist(package: dict) -> tuple[str, str, str, int | None]:
    name = canonicalize_name(package["name"])
    artifact = package.get("sdist")
    if not isinstance(artifact, dict):
        raise WheelhouseBuildError(
            f"No SHA256-locked compatible artifact: {name}=={package['version']}"
        )
    url = artifact.get("url", "")
    filename = artifact.get("name") or urllib.parse.unquote(
        urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
    )
    hashes = artifact.get("hashes", {})
    sha = hashes.get("sha256") if isinstance(hashes, dict) else None
    if (
        not filename
        or Path(filename).name != filename
        or not isinstance(sha, str)
        or len(sha) != 64
    ):
        raise WheelhouseBuildError(
            f"No SHA256-locked compatible artifact: {name}=={package['version']}"
        )
    if not filename.endswith((".tar.gz", ".zip")):
        raise WheelhouseBuildError(f"Unsupported locked sdist format: {name}")
    if urllib.parse.urlsplit(url).scheme not in ("https", "file"):
        raise WheelhouseBuildError(
            f"Locked sdist uses an unsupported URL scheme: {name}"
        )
    return filename, url, sha, artifact.get("size")


def _choose_registry_artifact(
    package: dict, compatibility: dict
) -> tuple[str, str, str, str, int | None]:
    try:
        filename, url, sha, size = _choose_wheel(package, compatibility)
        return "wheel", filename, url, sha, size
    except WheelhouseBuildError as wheel_error:
        try:
            filename, url, sha, size = _choose_sdist(package)
        except WheelhouseBuildError:
            raise wheel_error
        return "sdist", filename, url, sha, size


def _download_locked_artifact(
    url: str, destination: Path, expected: str, expected_size: int | None
) -> None:
    digest = hashlib.sha256()
    length = 0
    with (
        urllib.request.urlopen(url, timeout=90) as response,
        destination.open("xb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            length += len(chunk)
    if digest.hexdigest() != expected or (
        expected_size is not None and length != expected_size
    ):
        raise WheelhouseBuildError(
            f"Locked artifact integrity failed: {destination.name}"
        )


def _build_internal(
    uv: str, source: Path, target: Path, expected_name: str, expected_version: str
) -> str:
    before = set(target.glob("*.whl"))
    _run(
        [
            uv,
            "build",
            "--wheel",
            "--no-sources",
            "--python",
            sys.executable,
            "--out-dir",
            str(target),
            str(source),
        ],
        cwd=REPOSITORY_ROOT,
    )
    new = set(target.glob("*.whl")) - before
    if len(new) != 1:
        raise WheelhouseBuildError(f"Unexpected internal build output: {expected_name}")
    wheel = next(iter(new))
    name, version, _, _ = parse_wheel_filename(wheel.name)
    if name != canonicalize_name(expected_name) or str(version) != expected_version:
        raise WheelhouseBuildError(f"Internal wheel identity mismatch: {expected_name}")
    return wheel.name


def _build_requirements(paths: list[Path]) -> list[str]:
    requirements: set[str] = set()
    for path in paths:
        metadata = _read_toml(path / "pyproject.toml")
        for specification in metadata.get("build-system", {}).get("requires", []):
            requirement = Requirement(specification)
            if requirement.url or not any(
                item.operator == "==" for item in requirement.specifier
            ):
                raise WheelhouseBuildError(
                    f"Unpinned build dependency in {path.name}: {requirement.name}"
                )
            requirements.add(str(requirement))
    return sorted(requirements)


def _lock_build_dependencies(uv: str, requirements: list[str], staging: Path) -> dict:
    input_path = staging / "build-requirements.in"
    output_path = staging / "pylock.build.toml"
    input_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    _run(
        [
            uv,
            "pip",
            "compile",
            str(input_path),
            "--python",
            sys.executable,
            "--format",
            "pylock.toml",
            "--no-sources",
            "--output-file",
            str(output_path),
        ],
        cwd=REPOSITORY_ROOT,
    )
    lock = _read_toml(output_path)
    if lock.get("lock-version") != "1.0" or not isinstance(lock.get("packages"), list):
        raise WheelhouseBuildError("Build dependencies could not be locked")
    return lock


def _artifact_hashes(package: dict) -> tuple[str, ...]:
    hashes: set[str] = set()
    artifacts = list(package.get("wheels", []))
    sdist = package.get("sdist")
    if isinstance(sdist, dict):
        artifacts.append(sdist)
    for artifact in artifacts:
        values = artifact.get("hashes", {})
        sha = values.get("sha256") if isinstance(values, dict) else None
        if isinstance(sha, str) and len(sha) == 64:
            hashes.add(sha)
    return tuple(sorted(hashes))


def _write_build_constraints(build_lock: dict, destination: Path) -> Path:
    lines: list[str] = []
    for package in _active_packages(build_lock):
        if "directory" in package or not package.get("version"):
            raise WheelhouseBuildError(
                f"Unsupported build constraint source: {package['name']}"
            )
        hashes = _artifact_hashes(package)
        if not hashes:
            raise WheelhouseBuildError(
                f"Build constraint has no SHA256 artifacts: {package['name']}"
            )
        requirement = (
            f"{canonicalize_name(package['name'])}=={package['version']}"
            + "".join(f" --hash=sha256:{value}" for value in hashes)
        )
        lines.append(requirement)
    destination.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
    return destination


def _extract_sdist(archive: Path, destination: Path) -> Path:
    destination.mkdir()
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as source:
            source.extractall(destination, filter="data")
    elif archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as source:
            for item in source.infolist():
                path = Path(item.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise WheelhouseBuildError(
                        f"Unsafe locked sdist member: {archive.name}"
                    )
            source.extractall(destination)
    else:
        raise WheelhouseBuildError(f"Unsupported locked sdist format: {archive.name}")
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) == 1:
        source_root = roots[0]
    else:
        source_root = destination
    if not (
        (source_root / "pyproject.toml").is_file()
        or (source_root / "setup.py").is_file()
        or (source_root / "setup.cfg").is_file()
    ):
        raise WheelhouseBuildError(
            f"Locked sdist has no buildable project: {archive.name}"
        )
    return source_root


def _build_locked_sdist(
    uv: str,
    archive: Path,
    staging: Path,
    target: Path,
    constraints: Path,
    expected_name: str,
    expected_version: str,
) -> str:
    source_root = _extract_sdist(
        archive, staging / f"source-{canonicalize_name(expected_name)}"
    )
    before = set(target.glob("*.whl"))
    _run(
        [
            uv,
            "build",
            "--wheel",
            "--no-sources",
            "--python",
            sys.executable,
            "--build-constraint",
            str(constraints),
            "--require-hashes",
            "--out-dir",
            str(target),
            str(source_root),
        ],
        cwd=REPOSITORY_ROOT,
    )
    new = set(target.glob("*.whl")) - before
    if len(new) != 1:
        raise WheelhouseBuildError(
            f"Unexpected locked sdist build output: {expected_name}"
        )
    wheel = next(iter(new))
    name, version, _, _ = parse_wheel_filename(wheel.name)
    if name != canonicalize_name(expected_name) or str(version) != expected_version:
        raise WheelhouseBuildError(
            f"Locked sdist wheel identity mismatch: {expected_name}"
        )
    return wheel.name


def _registry_wheels(
    uv: str,
    packages: list[dict],
    staging: Path,
    target: Path,
    compatibility: dict,
    origins: dict[tuple[str, str], set[str]],
    build_constraints: Path,
) -> list[dict]:
    records: list[dict] = []
    sources = staging / "locked-sources"
    sources.mkdir()
    for package in packages:
        name = canonicalize_name(package["name"])
        version = str(package["version"])
        kind, filename, url, sha, size = _choose_registry_artifact(
            package, compatibility
        )
        if kind == "wheel":
            wheel = target / filename
            if wheel.exists():
                if _sha256(wheel) != sha:
                    raise WheelhouseBuildError(
                        f"Conflicting locked wheel for {name}=={version}"
                    )
            else:
                _download_locked_artifact(url, wheel, sha, size)
            records.append(
                {
                    "name": name,
                    "version": version,
                    "filename": filename,
                    "sha256": sha,
                    "origin": sorted(origins[(name, version)]),
                }
            )
            continue
        archive = sources / filename
        if not archive.exists():
            _download_locked_artifact(url, archive, sha, size)
        wheel_name = _build_locked_sdist(
            uv,
            archive,
            staging,
            target,
            build_constraints,
            name,
            version,
        )
        records.append(
            {
                "name": name,
                "version": version,
                "filename": wheel_name,
                "sha256": _sha256(target / wheel_name),
                "origin": sorted(origins[(name, version)]),
                "built_from": "sdist",
                "source_filename": filename,
                "source_sha256": sha,
            }
        )
    return records


def build_wheelhouse(*, profile: str, application: Path, uv: str) -> dict:
    _require_python()
    if profile not in _PROFILES:
        raise WheelhouseBuildError("Unknown Starter profile")
    application = application.expanduser().resolve()
    starter = _validate_starter(application, profile)
    destination = application / "wheelhouse"
    if destination.exists():
        raise WheelhouseBuildError(
            "Wheelhouse already exists; regenerate the Starter to rebuild"
        )
    product = _PRODUCTS[profile]
    project = REPOSITORY_ROOT / str(product["project_root"])
    package = product.get("export_package")
    package = str(package) if package else None
    compatibility = {tag: rank for rank, tag in enumerate(sys_tags())}
    with tempfile.TemporaryDirectory(prefix=".wheelhouse-", dir=application) as temp:
        staging = Path(temp)
        target = staging / "wheelhouse"
        target.mkdir()
        lock_path = staging / "pylock.runtime.toml"
        lock = _export_runtime_lock(uv, project, package, lock_path)
        selected = _active_packages(lock)
        local: list[tuple[dict, Path]] = []
        registry: list[dict] = []
        for entry in selected:
            if "directory" in entry:
                local.append((entry, _local_directory(entry, project, REPOSITORY_ROOT)))
            elif (entry.get("wheels") or entry.get("sdist")) and entry.get("version"):
                registry.append(entry)
            else:
                raise WheelhouseBuildError(
                    f"Unsupported locked dependency source: {entry['name']}"
                )
        root_package = canonicalize_name(str(product["root_package"]))
        if (
            sum(canonicalize_name(entry["name"]) == root_package for entry, _ in local)
            != 1
        ):
            raise WheelhouseBuildError(
                "Exported lock does not contain the expected root package"
            )
        build_reqs = _build_requirements([path for _, path in local] + [application])
        build_lock = _lock_build_dependencies(uv, build_reqs, staging)
        build_registry = _active_packages(build_lock)
        build_constraints = _write_build_constraints(
            build_lock, staging / "build-constraints.txt"
        )
        origins: dict[tuple[str, str], set[str]] = {}
        merged: dict[tuple[str, str], dict] = {}
        for origin, entries in [("runtime", registry), ("build", build_registry)]:
            for entry in entries:
                if (
                    "directory" in entry
                    or not (entry.get("wheels") or entry.get("sdist"))
                    or not entry.get("version")
                ):
                    raise WheelhouseBuildError(
                        f"Unsupported {origin} dependency: {entry['name']}"
                    )
                key = canonicalize_name(entry["name"]), str(entry["version"])
                if key in merged:
                    current = _choose_registry_artifact(merged[key], compatibility)
                    incoming = _choose_registry_artifact(entry, compatibility)
                    if current[:4] != incoming[:4]:
                        raise WheelhouseBuildError(
                            f"Conflicting locked artifacts for {key[0]}"
                        )
                merged[key] = entry
                origins.setdefault(key, set()).add(origin)
        records = _registry_wheels(
            uv,
            list(merged.values()),
            staging,
            target,
            compatibility,
            origins,
            build_constraints,
        )
        for entry, path in local:
            name = canonicalize_name(entry["name"])
            metadata = _read_toml(path / "pyproject.toml")["project"]
            version = str(metadata["version"])
            filename = _build_internal(uv, path, target, name, version)
            records.append(
                {
                    "name": name,
                    "version": version,
                    "filename": filename,
                    "sha256": _sha256(target / filename),
                    "origin": ["internal"],
                    "source": path.relative_to(REPOSITORY_ROOT).as_posix(),
                }
            )
        if len({record["filename"] for record in records}) != len(records):
            raise WheelhouseBuildError("Two packages produced the same wheel filename")
        git_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        metadata = {
            "schema_version": 1,
            "profile": profile,
            "python": PYTHON_VERSION,
            "platform": sys.platform,
            "machine": platform.machine(),
            "source_git_head": git_head,
            "runtime_lock_sha256": _sha256(lock_path),
            "build_requirements": build_reqs,
            "qualification": "UNVERIFIED",
            "packages": sorted(
                records, key=lambda item: (item["name"], item["version"])
            ),
        }
        (target / "manifest.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        target.rename(destination)
    try:
        starter["wheelhouse_included"] = True
        (application / "manifest.json").write_text(
            json.dumps(starter, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        shutil.rmtree(destination)
        raise
    return {
        "status": "BUILT_UNQUALIFIED",
        "profile": profile,
        "wheelhouse": str(destination),
        "packages": len(metadata["packages"]),
        "source_git_head": git_head,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a locked offline Web Starter wheelhouse"
    )
    parser.add_argument("--profile", required=True, choices=tuple(_PROFILES))
    parser.add_argument("--application", type=Path)
    args = parser.parse_args()
    root = args.application or (
        REPOSITORY_ROOT / "distribution" / f"{args.profile}-web-starter"
    )
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv executable is required")
    try:
        result = build_wheelhouse(profile=args.profile, application=root, uv=uv)
    except (WheelhouseBuildError, OSError, subprocess.CalledProcessError) as error:
        print(
            json.dumps(
                {"status": "BLOCKED", "profile": args.profile, "error": str(error)},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
