from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tomllib
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "distribution/processes/distribute.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_distribution_processes_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
distribution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = distribution
SPEC.loader.exec_module(distribution)


class BundleStub:
    class ProcessBundleError(RuntimeError):
        pass

    def __init__(
        self, roots: dict[str, Path], *, stale: set[str] | None = None
    ) -> None:
        self.roots = roots
        self.stale = stale or set()
        self.builds: list[str] = []
        self.output_roots: list[Path] = []

    def resolve_process_root(self, repository_root: Path, value: str) -> Path:
        try:
            return self.roots[value]
        except KeyError as error:
            raise self.ProcessBundleError(
                f"process project not found: {value}"
            ) from error

    def require_prepared_build_inputs(
        self,
        repository_root: Path,
        process_root: Path,
    ) -> Path:
        command = _command(process_root)
        if command in self.stale:
            raise self.ProcessBundleError(
                f"prepared build inputs are stale for {command}. "
                f"Run the local process tool with: prepare {command}"
            )
        return repository_root / f"artifacts/receipts/processes/{command}.json"

    def build_process_bundle(
        self,
        *,
        repository_root: Path,
        process_root: Path,
        output_root: Path,
    ) -> Path:
        command = _command(process_root)
        self.builds.append(command)
        self.output_roots.append(output_root.resolve())
        output = output_root / command
        shutil.copytree(process_root, output)
        (output / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        (output / "wheels").mkdir()
        return output


def _command(root: Path) -> str:
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return metadata["tool"]["atlanticus"]["container"]["command"]


def _write_source(root: Path, relative: str, name: str) -> Path:
    process = root / relative
    (process / "src/sample").mkdir(parents=True)
    (process / "src/sample/__init__.py").write_text("SOURCE = 1\n", encoding="utf-8")
    (process / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}-package"\n'
        'version = "1.0.0"\n'
        f'description = "Process {name}."\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        f'{name} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{name}"\n'
        'system-profile = "base"\n',
        encoding="utf-8",
    )
    (process / ".env.detail").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    (process / "config.detail.json").write_text("{}\n", encoding="utf-8")
    (process / "secrets.detail.json").write_text("[]\n", encoding="utf-8")
    return process


def _write_transport(root: Path) -> None:
    deployment = root / "deployment/processes"
    deployment.mkdir(parents=True)
    (deployment / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (deployment / ".dockerignore").write_text("*\n", encoding="utf-8")
    local = root / "deployment/local"
    scheduler = local / "scheduler"
    scheduler.mkdir(parents=True)
    (local / "simulation.py").write_text("VALUE = 1\n", encoding="utf-8")
    (scheduler / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (scheduler / "scheduler.py").write_text("VALUE = 1\n", encoding="utf-8")


def _patch_generation_context(monkeypatch, tmp_path: Path) -> None:
    template = tmp_path / "consumer"
    template.mkdir()
    for name in ("process.py", "process.sh", "process.cmd"):
        (template / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(distribution, "_consumer_template_root", lambda: template)
    monkeypatch.setattr(distribution, "_generated_at", lambda: "2026-09-22T23:30:00Z")
    monkeypatch.setattr(
        distribution,
        "_source_revision",
        lambda repository_root: "a7623b7589cd988bfea693e0a182640751ef52a6",
    )


def test_deployment_catalog_is_stable() -> None:
    assert [
        (item.number, item.process, item.execution_file)
        for item in distribution.DEPLOYMENT_CATALOG
    ] == [
        ("01", "operational-data-pi", "pi-web-api"),
        ("02", "operational-data-notpii", "notpii"),
        ("03", "operational-data-dispatch", "dispatch"),
        ("04", "operational-data-blockgrade", "blockgrade"),
        ("05", "operational-data-fabrica-planes", "fabrica-planes"),
        ("06", "operational-data-fabrica-kpis", "fabrica-kpis"),
        ("07", "operational-data-remanentes", "remanentes"),
        ("08", "operational-data-meteodata", "meteodata"),
        ("21", "ada-kpi-runtime", "kpis"),
        ("22", "ada-kpi-historian", "kpis-historian"),
        ("41", "ada-kpi-delivery", "kpis-delivery"),
        ("42", "ada-kpi-timeseries-delivery", "kpis-timeseries-delivery"),
    ]


def test_distribution_rebuilds_source_and_never_copies_mutable_qa_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    runtime = _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    qa_source = tmp_path / "artifacts/processes/ada-kpi-runtime/src"
    qa_source.mkdir(parents=True)
    (qa_source / "manual.py").write_text("QA_ONLY = 1\n", encoding="utf-8")
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub({"ada-kpi-runtime": runtime})

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="ada-generic",
        selections=("ada-kpi-runtime",),
        targets=(),
        bundle=bundle,
    )

    assert bundle.builds == ["ada-kpi-runtime"]
    assert all(
        not output_root.is_relative_to(tmp_path.resolve())
        for output_root in bundle.output_roots
    )
    assert (target / "processes/kpis/src/sample/__init__.py").is_file()
    assert not (target / "processes/kpis/src/manual.py").exists()


def test_distribution_blocks_stale_source_before_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    runtime = _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub(
        {"ada-kpi-runtime": runtime},
        stale={"ada-kpi-runtime"},
    )

    try:
        distribution.distribute(
            repository_root=tmp_path,
            output_root=tmp_path / "distribution",
            distribution_name="ada-generic",
            selections=("ada-kpi-runtime",),
            targets=(),
            bundle=bundle,
        )
    except distribution.DistributionError as error:
        assert "prepared build inputs are stale" in str(error)
    else:
        raise AssertionError("Expected stale prepare receipt to block distribution")

    assert bundle.builds == []


def test_mixed_source_scopes_keep_deployment_order(tmp_path: Path, monkeypatch) -> None:
    _write_transport(tmp_path)
    pi = _write_source(
        tmp_path,
        "scopes/operational-data/processes/pi",
        "operational-data-pi",
    )
    dispatch = _write_source(
        tmp_path,
        "scopes/operational-data/processes/dispatch",
        "operational-data-dispatch",
    )
    runtime = _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    delivery = _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-delivery",
        "ada-kpi-delivery",
    )
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub(
        {
            "operational-data-pi": pi,
            "operational-data-dispatch": dispatch,
            "ada-kpi-runtime": runtime,
            "ada-kpi-delivery": delivery,
        }
    )

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="ada-generic",
        selections=(
            "ada-kpi-delivery",
            "operational-data-dispatch",
            "ada-kpi-runtime",
            "operational-data-pi",
        ),
        targets=(),
        bundle=bundle,
    )

    services = json.loads((target / "services.json").read_text(encoding="utf-8"))
    assert [item["container_name"] for item in services] == [
        "job01",
        "job03",
        "job21",
        "job41",
    ]


def test_regeneration_preserves_retained_consumer_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    pi = _write_source(
        tmp_path,
        "scopes/operational-data/processes/pi",
        "operational-data-pi",
    )
    runtime = _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub(
        {
            "operational-data-pi": pi,
            "ada-kpi-runtime": runtime,
        }
    )

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="consumer",
        selections=("operational-data-pi", "ada-kpi-runtime"),
        targets=(),
        bundle=bundle,
    )
    retained = target / "processes/kpis"
    for name in distribution.CONSUMER_CONFIGURATION_FILES:
        (retained / name).write_text(f"{name}\n", encoding="utf-8")

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="consumer",
        selections=("ada-kpi-runtime",),
        targets=(),
        bundle=bundle,
    )

    for name in distribution.CONSUMER_CONFIGURATION_FILES:
        assert (target / "processes/kpis" / name).read_text() == f"{name}\n"
    assert not (target / "processes/pi-web-api").exists()


def test_distribution_keeps_local_deployment_assets_out_of_root(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    runtime = _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub({"ada-kpi-runtime": runtime})

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="ada-generic",
        selections=("ada-kpi-runtime",),
        targets=(),
        bundle=bundle,
    )

    assert (target / "Dockerfile").is_file()
    assert (target / ".dockerignore").is_file()
    assert not (target / "compose.yaml").exists()
    assert not (target / "compose.bind.yaml").exists()
    assert (target / "deployment/local/compose.yaml").is_file()
    assert (target / "deployment/local/compose.bind.yaml").is_file()
    assert (target / "deployment/local/simulation.py").is_file()
    assert (target / "deployment/local/scheduler/Dockerfile").is_file()
    assert (target / "deployment/local/scheduler/scheduler.py").is_file()


def test_split_fabrica_distribution_preserves_contiguous_slots(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    roots = {
        command: _write_source(
            tmp_path,
            f"scopes/operational-data/processes/{folder}",
            command,
        )
        for command, folder in (
            ("operational-data-fabrica-planes", "fabrica-planes"),
            ("operational-data-fabrica-kpis", "fabrica-kpis"),
            ("operational-data-remanentes", "remanentes"),
        )
    }
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub(roots)

    combined = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="fabrica-combined",
        selections=tuple(reversed(tuple(roots))),
        targets=(),
        bundle=bundle,
    )
    services = json.loads((combined / "services.json").read_text(encoding="utf-8"))
    assert [
        (item["container_name"], item["execution_file"], item["config_file"])
        for item in services
    ] == [
        ("job05", "fabrica-planes", "processes/fabrica-planes/config.json"),
        ("job06", "fabrica-kpis", "processes/fabrica-kpis/config.json"),
        ("job07", "remanentes", "processes/remanentes/config.json"),
    ]
    manifest = json.loads((combined / "distribution.json").read_text(encoding="utf-8"))
    assert [
        (item["process"], item["deployment"]["container_name"])
        for item in manifest["processes"]
    ] == [
        ("operational-data-fabrica-planes", "job05"),
        ("operational-data-fabrica-kpis", "job06"),
        ("operational-data-remanentes", "job07"),
    ]

    for command, expected_job in (
        ("operational-data-fabrica-planes", "job05"),
        ("operational-data-fabrica-kpis", "job06"),
    ):
        independent = distribution.distribute(
            repository_root=tmp_path,
            output_root=tmp_path / "distribution",
            distribution_name=command,
            selections=(command,),
            targets=(),
            bundle=bundle,
        )
        independent_services = json.loads(
            (independent / "services.json").read_text(encoding="utf-8")
        )
        assert len(independent_services) == 1
        assert independent_services[0]["container_name"] == expected_job
        assert independent_services[0]["execution_file"] == command.removeprefix(
            "operational-data-"
        )


def test_meteodata_distribution_preserves_job08_in_single_and_combined_exports(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    pi = _write_source(
        tmp_path,
        "scopes/operational-data/processes/pi",
        "operational-data-pi",
    )
    meteodata = _write_source(
        tmp_path,
        "scopes/operational-data/processes/meteodata",
        "operational-data-meteodata",
    )
    _patch_generation_context(monkeypatch, tmp_path)
    bundle = BundleStub(
        {
            "operational-data-pi": pi,
            "operational-data-meteodata": meteodata,
        }
    )

    single = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="meteodata-single",
        selections=("operational-data-meteodata",),
        targets=(),
        bundle=bundle,
    )
    single_services = json.loads((single / "services.json").read_text(encoding="utf-8"))
    assert len(single_services) == 1
    assert single_services[0]["container_name"] == "job08"
    assert single_services[0]["execution_file"] == "meteodata"
    assert single_services[0]["config_file"] == "processes/meteodata/config.json"
    assert "execution_file" in single_services[0]
    assert "excecution_file" not in single_services[0]
    assert (single / "processes/meteodata/config.detail.json").is_file()

    combined = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="operational-pair",
        selections=("operational-data-meteodata", "operational-data-pi"),
        targets=(),
        bundle=bundle,
    )
    combined_services = json.loads(
        (combined / "services.json").read_text(encoding="utf-8")
    )
    assert [
        (item["container_name"], item["execution_file"]) for item in combined_services
    ] == [
        ("job01", "pi-web-api"),
        ("job08", "meteodata"),
    ]
    manifest = json.loads((combined / "distribution.json").read_text(encoding="utf-8"))
    assert all(
        "execution_file" in item["deployment"]
        and "excecution_file" not in item["deployment"]
        for item in manifest["processes"]
    )
    assert [
        (item["process"], item["deployment"]["container_name"])
        for item in manifest["processes"]
    ] == [
        ("operational-data-pi", "job01"),
        ("operational-data-meteodata", "job08"),
    ]
