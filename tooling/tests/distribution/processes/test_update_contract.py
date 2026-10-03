from __future__ import annotations

import importlib
import json
import sys
import tomllib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SOURCE = PROJECT_ROOT / "tooling/distribution/processes"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / "consumer"))
producer = importlib.import_module("update_package")
contract = importlib.import_module("update_contract")
consumer_tool = importlib.import_module("update")


def project(
    *,
    process: str,
    package: str,
    dependency_version: str = "1.0.0",
    resources: str = "",
    extra: str = "",
) -> str:
    return (
        "[project]\n"
        f'name = "{package}"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        f'dependencies = ["atlanticus-http=={dependency_version}"]\n'
        "[dependency-groups]\n"
        f'bundle-internal = ["atlanticus-http=={dependency_version}"]\n'
        "[project.scripts]\n"
        f'{process} = "sample:main"\n'
        "[tool.atlanticus.container]\n"
        f'command = "{process}"\n'
        'system-profile = "base"\n'
        f"{resources}"
        "[tool.uv]\n"
        "default-groups = []\n"
        "[tool.uv.sources]\n"
        f'atlanticus-http = {{ path = "wheels/atlanticus_http-{dependency_version}-py3-none-any.whl" }}\n'
        f"{extra}"
    )


def entry(category: str):
    command, package, alias, other = (
        ("ada-kpi-runtime", "ada-kpi-runtime-process", "kpis-runtime", "kpis-historian")
        if category == "kpi"
        else (
            "operational-data-pi",
            "atlanticus-operational-data-pi-process",
            "pi-web-api",
            "meteodata",
        )
    )
    return command, package, alias, other


def setup(tmp_path: Path, category: str = "pi"):
    command, package, alias, other_alias = entry(category)
    existing = tmp_path / "consumer"
    process_dir = existing / "processes" / alias
    process_dir.mkdir(parents=True)
    (existing / "processes" / other_alias).mkdir()
    (existing / "processes" / other_alias / "unchanged.txt").write_text(
        "other-process-stays"
    )
    (process_dir / "pyproject.toml").write_text(
        project(process=command, package=package)
    )
    (process_dir / "uv.lock").write_text("version = 1\n# baseline\n")
    (process_dir / "wheels").mkdir()
    (process_dir / "wheels/atlanticus_http-1.0.0-py3-none-any.whl").write_bytes(
        b"old immutable wheel"
    )
    (process_dir / "src").mkdir()
    (process_dir / "src/main.py").write_text("LOCAL_PROCESS_CUSTOMIZATION = 42\n")
    (process_dir / "src/catalog.py").write_text("CATALOG_READER = True\n")
    (process_dir / ".env").write_text("SECRET=never-update\n")
    (process_dir / "config.json").write_text('{"value":"local"}')
    (process_dir / "secrets.json").write_text('{"never":"change"}')
    (process_dir / ".env.detail").write_text("baseline-template")
    (process_dir / "operational-catalog.json").write_text('{"keep":true}')
    meta = {
        "schema_version": 1,
        "name": "sample",
        "source": {"repository": "atlanticus", "revision": "a" * 40},
        "processes": [
            {
                "process": command,
                "project": package,
                "version": "1.0.0",
                "runtime": {"language": "python", "version": "3.14.2"},
                "deployment": {"execution_file": alias, "container_name": "job01"},
            },
            {
                "process": "other-process",
                "project": "other-process",
                "version": "1.0.0",
                "runtime": {"language": "python", "version": "3.14.2"},
                "deployment": {
                    "execution_file": other_alias,
                    "container_name": "job02",
                },
            },
        ],
    }
    (existing / "distribution.json").write_text(json.dumps(meta))
    newer = tmp_path / "built" / alias
    newer.mkdir(parents=True)
    (newer / "pyproject.toml").write_text(
        project(process=command, package=package, dependency_version="1.1.0")
    )
    (newer / "uv.lock").write_text("version = 1\n# target\n")
    (newer / "wheels").mkdir()
    (newer / "wheels/atlanticus_http-1.1.0-py3-none-any.whl").write_bytes(
        b"new immutable wheel"
    )
    (newer / "src").mkdir()
    (newer / "src/main.py").write_text("UPSTREAM_SOURCE_MUST_NOT_BE_PUBLISHED = True\n")
    (newer / ".env.detail").write_text("upstream-template-must-not-change")
    source = {"repository": "atlanticus", "revision": "b" * 40}

    def distribute(**kwargs):
        archive_path = kwargs["output_root"] / "sample.extension.zip"
        with zipfile.ZipFile(archive_path, "w") as zip_file:
            updated = dict(meta["processes"][0])
            zip_file.writestr(
                "extension.json", json.dumps({"source": source, "processes": [updated]})
            )
            zip_file.writestr("processes/", b"")
            zip_file.writestr(f"processes/{alias}/", b"")
            for child in sorted(newer.rglob("*")):
                name = f"processes/{alias}/{child.relative_to(newer).as_posix()}"
                if child.is_dir():
                    zip_file.writestr(name + "/", b"")
                else:
                    zip_file.write(child, name)
        return archive_path

    def validate(root, require_environment=False):
        assert (root / "processes" / alias / "src/main.py").is_file()
        assert (
            root / "processes" / other_alias / "unchanged.txt"
        ).read_text() == "other-process-stays"
        assert (root / "processes" / alias / "wheels").is_dir()

    helper = SimpleNamespace(
        distribute=distribute,
        _validate_distribution=validate,
        _manifest=lambda root: json.loads((root / "distribution.json").read_text()),
    )
    return existing, newer, helper, command, alias


def generate(tmp_path: Path, category: str = "pi"):
    root, newer, helper, command, alias = setup(tmp_path, category)
    path = producer.create_update(
        builder=helper,
        repository_root=tmp_path,
        baseline_root=root,
        distribution_name="sample",
        process=command,
        output_root=tmp_path / "output",
    )
    return root, newer, helper, command, alias, path


@pytest.mark.parametrize("category", ["pi", "kpi"])
def test_generate_inspect_apply_preserve_exact_process_source_and_operational_files(
    tmp_path: Path, category: str
):
    root, _, helper, _, alias, archive_path = generate(tmp_path, category)
    baseline = {
        name: (root / "processes" / alias / name).read_bytes()
        for name in (
            "src/main.py",
            "src/catalog.py",
            ".env",
            "config.json",
            "secrets.json",
            ".env.detail",
            "operational-catalog.json",
        )
    }
    distro = (root / "distribution.json").read_bytes()
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.namelist()
        assert all(
            not name.endswith(
                ("main.py", "catalog.py", "config.json", "secrets.json", ".env.detail")
            )
            for name in entries
        )
        assert entries == [
            name
            for name in entries
            if name == "update.json" or name.startswith("processes/")
        ]
    plan = consumer_tool.inspect_update(root, archive_path, helper)
    assert plan.manifest["kind"] == "dependency-update"
    assert plan.manifest["changed_wheels"] == [
        {"name": "atlanticus-http", "from": "1.0.0", "to": "1.1.0"}
    ]
    backup = consumer_tool.apply_update(root, archive_path, helper)
    assert (backup / "previous/pyproject.toml").is_file()
    assert (backup / "previous/uv.lock").is_file()
    assert (backup / "previous/wheels").is_dir()
    assert not (backup / "previous/src").exists()
    assert (root / "distribution.json").read_bytes() == distro
    assert (
        (root / "processes/meteodata/unchanged.txt").read_text()
        == "other-process-stays"
        if category == "pi"
        else (root / "processes/kpis-historian/unchanged.txt").read_text()
        == "other-process-stays"
    )
    for name, value in baseline.items():
        assert (root / "processes" / alias / name).read_bytes() == value
    current = root / "processes" / alias
    assert tomllib.loads((current / "pyproject.toml").read_text())["project"][
        "dependencies"
    ] == ["atlanticus-http==1.1.0"]
    assert (current / "uv.lock").read_text() == "version = 1\n# target\n"
    assert (
        list((current / "wheels").glob("*.whl"))[0].name
        == "atlanticus_http-1.1.0-py3-none-any.whl"
    )
    with pytest.raises(consumer_tool.ProcessUpdateError, match="baseline"):
        consumer_tool.inspect_update(root, archive_path, helper)


def test_customized_process_source_does_not_block_dependencies(tmp_path: Path):
    root, _, helper, _, alias, archive_path = generate(tmp_path)
    path = root / "processes" / alias / "src/main.py"
    path.write_text("SPECIAL_CASE_FOR_DEPLOYED_INSTANCE = True\n")
    consumer_tool.apply_update(root, archive_path, helper)
    assert path.read_text() == "SPECIAL_CASE_FOR_DEPLOYED_INSTANCE = True\n"


def test_non_dependency_pyproject_change_is_rejected(tmp_path: Path):
    root, newer, helper, command, _ = setup(tmp_path)
    path = newer / "pyproject.toml"
    path.write_text(
        path.read_text().replace(
            'system-profile = "base"', 'system-profile = "sqlserver"'
        )
    )
    with pytest.raises(producer.ProcessUpdateError, match="Non-dependency"):
        producer.create_update(
            builder=helper,
            repository_root=tmp_path,
            baseline_root=root,
            distribution_name="sample",
            process=command,
            output_root=tmp_path / "out",
        )


def test_process_version_change_requires_separate_strategy(tmp_path: Path):
    root, newer, helper, command, _ = setup(tmp_path)
    path = newer / "pyproject.toml"
    path.write_text(path.read_text().replace('version = "1.0.0"', 'version = "1.0.1"'))
    with pytest.raises(
        producer.ProcessUpdateError, match="version|identity|Non-dependency"
    ):
        producer.create_update(
            builder=helper,
            repository_root=tmp_path,
            baseline_root=root,
            distribution_name="sample",
            process=command,
            output_root=tmp_path / "out",
        )


def rewrite_archive(
    archive_path: Path,
    target: Path,
    *,
    added: tuple[str, bytes] | None = None,
    corrupt: str | None = None,
):
    with zipfile.ZipFile(archive_path) as original:
        with zipfile.ZipFile(target, "w") as output:
            for member in original.infolist():
                content = original.read(member)
                if corrupt == member.filename:
                    content = b"TAMPERED"
                output.writestr(member, content)
            if added:
                output.writestr(*added)


@pytest.mark.parametrize(
    "extra",
    [
        "processes/pi-web-api/src/main.py",
        "processes/pi-web-api/config.json",
        "../escape.txt",
    ],
)
def test_extra_source_configuration_or_traversal_is_rejected(
    tmp_path: Path, extra: str
):
    root, _, helper, _, alias, archive_path = generate(tmp_path)
    altered = tmp_path / "unexpected.zip"
    rewrite_archive(archive_path, altered, added=(extra, b"inject"))
    with pytest.raises(consumer_tool.ProcessUpdateError):
        consumer_tool.apply_update(root, altered, helper)
    assert (
        root / "processes" / alias / "src/main.py"
    ).read_text() == "LOCAL_PROCESS_CUSTOMIZATION = 42\n"
    assert not (root / ".updates/.lock").exists()


def test_corrupt_dependency_payload_or_changed_installed_lock_rejected(tmp_path: Path):
    root, _, helper, _, alias, archive_path = generate(tmp_path)
    altered = tmp_path / "corrupt.zip"
    rewrite_archive(archive_path, altered, corrupt=f"processes/{alias}/uv.lock")
    with pytest.raises(consumer_tool.ProcessUpdateError, match="integrity"):
        consumer_tool.apply_update(root, altered, helper)
    (root / "processes" / alias / "uv.lock").write_text("version = 2\n")
    with pytest.raises(consumer_tool.ProcessUpdateError, match="baseline"):
        consumer_tool.apply_update(root, archive_path, helper)


def test_wheel_version_immutability_is_enforced(tmp_path: Path):
    root, newer, helper, command, _ = setup(tmp_path)
    for wheel in (newer / "wheels").iterdir():
        wheel.unlink()
    (newer / "wheels/atlanticus_http-1.0.0-py3-none-any.whl").write_bytes(
        b"mutated wheel"
    )
    path = newer / "pyproject.toml"
    path.write_text(path.read_text().replace("1.1.0", "1.0.0"))
    with pytest.raises(producer.ProcessUpdateError, match="without a version bump"):
        producer.create_update(
            builder=helper,
            repository_root=tmp_path,
            baseline_root=root,
            distribution_name="sample",
            process=command,
            output_root=tmp_path / "out",
        )


def test_apply_rolls_back_only_dependencies_on_final_validation_error(tmp_path: Path):
    root, _, helper, _, alias, archive_path = generate(tmp_path)
    current = root / "processes" / alias
    old = contract.fingerprint(contract.inventory(current))

    def fail_validate(root, require_environment=False):
        raise RuntimeError("synthetic validator failure")

    helper._validate_distribution = fail_validate
    with pytest.raises(RuntimeError, match="synthetic"):
        consumer_tool.apply_update(root, archive_path, helper)
    assert contract.fingerprint(contract.inventory(current)) == old
    assert (current / "src/main.py").read_text() == "LOCAL_PROCESS_CUSTOMIZATION = 42\n"
    assert not (root / ".updates/.lock").exists()
