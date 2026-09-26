from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path

REPOSITORY_ENVIRONMENT_VARIABLE = "ATLANTICUS_WHEEL_REPOSITORY"
REPOSITORY_RELATIVE_PATH = Path("wheelhouse")
RECORD_SCHEMA_VERSION = 1
SUPPORTED_SOURCE_ROOTS = ("backend", "connectivity", "integrations", "scopes", "web")
BUILD_PYTHON_VERSION = "3.14.2"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[A-Za-z0-9._+!-]*[A-Za-z0-9])?$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


# Señala fallos de integridad, conflictos de versiones y errores de publicación.
class WheelRepositoryError(RuntimeError):
    pass


# Captura identidad, dependencia transitiva y huella del wheel publicado.
@dataclass(frozen=True, slots=True)
class WheelRecord:
    name: str
    version: str
    dependencies: tuple[str, ...]
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
# Describe un proyecto construible sin confundirlo con un workspace ni un artefacto generado.
class WheelProject:
    name: str
    version: str
    root: Path


# Normaliza identidades para que guiones, puntos y subrayados no dupliquen registros.
def canonicalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# Fija la autoridad de wheels en este checkout y rechaza overrides externos o symlinks.
def wheel_repository_path(repository_root: Path) -> Path:
    path = repository_root.resolve() / REPOSITORY_RELATIVE_PATH
    if path.is_symlink():
        raise WheelRepositoryError(f"Atlanticus wheelhouse cannot be a symlink: {path}")
    configured = os.environ.get(REPOSITORY_ENVIRONMENT_VARIABLE)
    if configured and Path(configured).expanduser().resolve() != path:
        raise WheelRepositoryError(
            f"{REPOSITORY_ENVIRONMENT_VARIABLE} must point to the Atlanticus wheelhouse: {path}"
        )
    return path


# Inspecciona metadatos dentro del wheel sin extraer ni ejecutar código del paquete.
def _wheel_metadata(path: Path) -> tuple[str, str, tuple[str, ...]]:
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_files = [
                info for info in archive.infolist()
                if info.filename.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1 or metadata_files[0].file_size > 1_000_000:
                raise WheelRepositoryError(f"Wheel metadata is invalid: {path}")
            if archive.testzip() is not None:
                raise WheelRepositoryError(f"Wheel archive checksum failed: {path}")
            message = BytesParser().parsebytes(archive.read(metadata_files[0]))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise WheelRepositoryError(f"Could not read wheel: {path}") from error
    name = message.get("Name")
    version = message.get("Version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise WheelRepositoryError(f"Wheel name or version is missing: {path}")
    name = canonicalize_package_name(name)
    if not NAME_PATTERN.fullmatch(name) or not VERSION_PATTERN.fullmatch(version):
        raise WheelRepositoryError(f"Wheel package name or version is invalid: {path}")
    filename = path.name
    parts = filename.removesuffix(".whl").split("-")
    if (
        not filename.endswith(".whl")
        or len(parts) not in (5, 6)
        or canonicalize_package_name(parts[0]) != name
        or parts[1] != version
    ):
        raise WheelRepositoryError(f"Wheel filename disagrees with metadata: {path}")
    return name, version, tuple(message.get_all("Requires-Dist", []))


# Recorre el wheel por bloques para verificar su integridad sin cargarlo en memoria.
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Gestiona publicaciones inmutables y resoluciones exactas por nombre y versión.
class WheelRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def has_package(self, name: str) -> bool:
        canonical = canonicalize_package_name(name)
        return NAME_PATTERN.fullmatch(canonical) is not None and (self.root / canonical).is_dir()

    def resolve(self, name: str, version: str) -> WheelRecord | None:
        canonical = canonicalize_package_name(name)
        if not NAME_PATTERN.fullmatch(canonical) or not VERSION_PATTERN.fullmatch(version):
            raise WheelRepositoryError(f"Invalid wheel identity: {name}=={version}")
        release_root = self.root / canonical / version
        if not release_root.exists():
            return None
        if not release_root.is_dir() or release_root.is_symlink():
            raise WheelRepositoryError(f"Invalid wheel repository release: {release_root}")
        record_path = release_root / "record.json"
        if record_path.is_symlink():
            raise WheelRepositoryError(f"Unsafe wheel release record: {release_root}")
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise WheelRepositoryError(f"Wheel release record is invalid: {release_root}") from error
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != RECORD_SCHEMA_VERSION
            or payload.get("name") != canonical
            or payload.get("version") != version
            or not isinstance(payload.get("filename"), str)
            or Path(payload["filename"]).name != payload["filename"]
            or not payload["filename"].endswith(".whl")
            or not isinstance(payload.get("sha256"), str)
            or not SHA256_PATTERN.fullmatch(payload["sha256"])
        ):
            raise WheelRepositoryError(f"Wheel release record is invalid: {release_root}")
        wheel_path = release_root / payload["filename"]
        if wheel_path.is_symlink() or not wheel_path.is_file():
            raise WheelRepositoryError(f"Wheel release is missing or unsafe: {release_root}")
        if sorted(path.name for path in release_root.iterdir()) != sorted(
            ("record.json", payload["filename"])
        ):
            raise WheelRepositoryError(f"Unexpected files in wheel release: {release_root}")
        if _sha256(wheel_path) != payload["sha256"]:
            raise WheelRepositoryError(f"Wheel release checksum mismatch: {wheel_path}")
        recorded_name, recorded_version, dependencies = _wheel_metadata(wheel_path)
        if recorded_name != canonical or recorded_version != version:
            raise WheelRepositoryError(f"Wheel release metadata mismatch: {wheel_path}")
        return WheelRecord(canonical, version, dependencies, wheel_path, payload["sha256"])

    def publish(self, wheel_path: Path) -> WheelRecord:
        if not wheel_path.is_file() or wheel_path.is_symlink():
            raise WheelRepositoryError(f"Wheel is not a regular file: {wheel_path}")
        name, version, _ = _wheel_metadata(wheel_path)
        digest = _sha256(wheel_path)
        existing = self.resolve(name, version)
        if existing is not None:
            if existing.sha256 != digest:
                raise WheelRepositoryError(
                    f"Wheel version is immutable: {name}=={version}"
                )
            return existing
        package_root = self.root / name
        package_root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=package_root))
        release_root = package_root / version
        try:
            copied = stage / wheel_path.name
            shutil.copyfile(wheel_path, copied)
            if _sha256(copied) != digest:
                raise WheelRepositoryError(f"Wheel changed during publication: {wheel_path}")
            (stage / "record.json").write_text(
                json.dumps(
                    {
                        "schema_version": RECORD_SCHEMA_VERSION,
                        "name": name,
                        "version": version,
                        "filename": wheel_path.name,
                        "sha256": digest,
                    },
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            try:
                stage.rename(release_root)
            except OSError as error:
                existing = self.resolve(name, version)
                if existing is None or existing.sha256 != digest:
                    raise WheelRepositoryError(
                        f"Could not publish immutable wheel: {name}=={version}"
                    ) from error
                return existing
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        published = self.resolve(name, version)
        if published is None:
            raise WheelRepositoryError(f"Wheel publication failed: {name}=={version}")
        return published

    def copy(self, record: WheelRecord, destination: Path) -> Path:
        current = self.resolve(record.name, record.version)
        if current is None or current.sha256 != record.sha256:
            raise WheelRepositoryError(f"Wheel changed after resolution: {record.name}")
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / record.path.name
        if target.exists():
            raise WheelRepositoryError(f"Wheel filename collision: {target.name}")
        shutil.copy2(current.path, target)
        if _sha256(target) != record.sha256:
            target.unlink(missing_ok=True)
            raise WheelRepositoryError(f"Wheel changed while copying: {record.name}")
        return target


# Descubre módulos con build-system en los cinco dominios de código fuente, incluyendo procesos.
def discover_wheel_projects(repository_root: Path) -> tuple[WheelProject, ...]:
    repository_root = repository_root.resolve()
    discovered: dict[str, WheelProject] = {}
    excluded = {"artifacts", ".git", ".venv", "build", "dist", "commented", "tests", "__pycache__"}
    for root_name in SUPPORTED_SOURCE_ROOTS:
        source_root = repository_root / root_name
        if not source_root.is_dir():
            continue
        if not source_root.resolve().is_relative_to(repository_root):
            raise WheelRepositoryError(f"Unsafe source root: {source_root}")
        for base, directories, files in os.walk(source_root):
            directories[:] = sorted(
                name for name in directories
                if name not in excluded and not (Path(base) / name).is_symlink()
            )
            if "pyproject.toml" not in files:
                continue
            config_path = Path(base) / "pyproject.toml"
            if config_path.is_symlink() or not config_path.resolve().is_relative_to(repository_root):
                raise WheelRepositoryError(f"Unsafe source project: {config_path}")
            relative = config_path.relative_to(repository_root)
            if any(part in {"artifacts", ".venv", "build", "dist", "commented", "tests"} for part in relative.parts):
                continue
            try:
                with config_path.open("rb") as stream:
                    metadata = tomllib.load(stream)
            except (OSError, tomllib.TOMLDecodeError) as error:
                raise WheelRepositoryError(f"Could not read project: {config_path}") from error
            project = metadata.get("project")
            build_system = metadata.get("build-system")
            uv_settings = metadata.get("tool", {}).get("uv", {})
            if not isinstance(project, dict) or not isinstance(build_system, dict):
                continue
            if isinstance(uv_settings, dict) and uv_settings.get("package") is False:
                continue
            if not isinstance(build_system.get("build-backend"), str):
                raise WheelRepositoryError(f"Build backend is missing: {config_path}")
            name, version = project.get("name"), project.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                raise WheelRepositoryError(f"Wheel project name or version is missing: {config_path}")
            canonical = canonicalize_package_name(name)
            if not NAME_PATTERN.fullmatch(canonical) or not VERSION_PATTERN.fullmatch(version):
                raise WheelRepositoryError(f"Invalid wheel project identity: {config_path}")
            if canonical in discovered:
                raise WheelRepositoryError(
                    f"Duplicate wheel project {canonical}: {discovered[canonical].root} and {config_path.parent}"
                )
            discovered[canonical] = WheelProject(canonical, version, config_path.parent)
    return tuple(discovered[name] for name in sorted(discovered))


# Construye todos los wheels antes de publicar y comprueba colisiones inmutables.
def build_and_publish_projects(
    repository_root: Path,
    store: WheelRepository,
    projects: tuple[WheelProject, ...],
) -> tuple[WheelRecord, ...]:
    if not projects:
        raise WheelRepositoryError("No wheel projects selected")
    repository_root = repository_root.resolve()
    with tempfile.TemporaryDirectory(prefix="atlanticus-wheels-") as temporary:
        built: list[tuple[WheelProject, Path]] = []
        # Las instalaciones y los locks de proceso no intervienen al construir wheels de biblioteca.
        for project in projects:
            output = Path(temporary) / project.name
            output.mkdir()
            command = (
                "uv", "build", str(project.root), "--wheel", "--out-dir", str(output),
                "--clear", "--no-sources", "--python", BUILD_PYTHON_VERSION,
                "--refresh", "--no-cache",
            )
            completed = subprocess.run(command, cwd=repository_root, check=False)
            if completed.returncode != 0:
                raise WheelRepositoryError(f"Wheel build failed: {project.name}=={project.version}")
            candidates = tuple(output.glob("*.whl"))
            if len(candidates) != 1:
                raise WheelRepositoryError(f"Expected exactly one wheel for {project.name}")
            built_name, built_version, _ = _wheel_metadata(candidates[0])
            if (built_name, built_version) != (project.name, project.version):
                raise WheelRepositoryError(f"Built wheel identity mismatch: {project.name}=={project.version}")
            built.append((project, candidates[0]))
        # Evita publicaciones parciales por conflicto de contenido ya registrado.
        for project, wheel in built:
            prior = store.resolve(project.name, project.version)
            if prior is not None and prior.sha256 != _sha256(wheel):
                raise WheelRepositoryError(
                    f"Wheel version is immutable: {project.name}=={project.version}"
                )
        return tuple(store.publish(wheel) for _, wheel in built)


# CLI explícita: inventario, publicación de archivo ya construido o construcción integral.
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build and publish immutable Atlanticus wheels.")
    parser.add_argument("action", choices=("publish", "list", "build-all"))
    parser.add_argument("wheels", nargs="*")
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--select", action="append", default=[])
    arguments = parser.parse_args(argv)
    repository_root = (
        arguments.source_root.resolve()
        if arguments.source_root is not None
        else Path(__file__).resolve().parents[2]
    )
    try:
        if arguments.action == "publish":
            if not arguments.wheels or arguments.select or arguments.source_root:
                parser.error("publish expects one or more wheel filenames")
        elif arguments.wheels:
            parser.error("list and build-all do not take wheel filenames")
        if arguments.action != "publish":
            projects = discover_wheel_projects(repository_root)
            requested = {canonicalize_package_name(name) for name in arguments.select}
            unknown = requested - {project.name for project in projects}
            if unknown:
                raise WheelRepositoryError("Unknown wheel projects: " + ", ".join(sorted(unknown)))
            selected = tuple(project for project in projects if not requested or project.name in requested)
            if arguments.action == "list":
                for project in selected:
                    print(f"{project.name}=={project.version} {project.root.relative_to(repository_root)}")
                print(f"Wheel projects: {len(selected)}")
                return 0
        location = arguments.repository or wheel_repository_path(repository_root)
        if not location.is_absolute():
            parser.error("--repository must be an absolute path")
        store = WheelRepository(location)
        if arguments.action == "publish":
            published = tuple(store.publish(Path(filename)) for filename in arguments.wheels)
        else:
            published = build_and_publish_projects(repository_root, store, selected)
        for record in published:
            print(f"Published {record.name}=={record.version}: {record.path}")
        print(f"Wheel releases: {len(published)}")
    except WheelRepositoryError as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
