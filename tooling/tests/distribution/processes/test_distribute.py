from __future__ import annotations

import importlib.util
import json
import sys
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


def _write_process(root: Path, name: str, project: str = "sample-process") -> None:
    process = root / "artifacts/processes" / name
    (process / "wheels").mkdir(parents=True)
    (process / "src").mkdir()
    (process / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{project}"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        f'{name} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{name}"\n'
        'system-profile = "base"\n',
        encoding="utf-8",
    )
    (process / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (process / ".env.detail").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    (process / "config.detail.json").write_text("{}\n", encoding="utf-8")
    (process / "secrets.detail.json").write_text("[]\n", encoding="utf-8")


def _write_source(root: Path, relative: str, name: str) -> None:
    process = root / relative
    process.mkdir(parents=True)
    (process / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}-package"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        f'{name} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{name}"\n'
        'system-profile = "base"\n',
        encoding="utf-8",
    )


def _write_transport(root: Path) -> None:
    deployment = root / "deployment/processes"
    deployment.mkdir(parents=True)
    (deployment / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (deployment / ".dockerignore").write_text("*\n", encoding="utf-8")


def _patch_consumer_template(monkeypatch, tmp_path: Path) -> None:
    template = tmp_path / "consumer"
    template.mkdir()
    for name in ("process.py", "process.sh", "process.cmd"):
        (template / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(distribution, "_consumer_template_root", lambda: template)


def test_mixed_explicit_processes_form_one_distribution(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    for name in (
        "operational-data-pi",
        "operational-data-dispatch",
        "ada-kpi-runtime",
        "ada-kpi-delivery",
    ):
        _write_process(tmp_path, name, project=f"{name}-package")
    _patch_consumer_template(monkeypatch, tmp_path)

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distributed",
        distribution_name="ada-generic",
        selections=(
            "operational-data-pi",
            "operational-data-dispatch",
            "ada-kpi-runtime",
            "ada-kpi-delivery",
        ),
        targets=(),
    )

    manifest = json.loads((target / "distribution.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in manifest["processes"]] == [
        "operational-data-pi",
        "operational-data-dispatch",
        "ada-kpi-runtime",
        "ada-kpi-delivery",
    ]
    assert not (target / ".runtime").exists()
    assert (target / "compose.yaml").is_file()
    assert (target / "compose.bind.yaml").is_file()


def test_regeneration_preserves_retained_consumer_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    for name in ("operational-data-pi", "ada-kpi-runtime"):
        _write_process(tmp_path, name)
    _patch_consumer_template(monkeypatch, tmp_path)

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distributed",
        distribution_name="consumer",
        selections=("operational-data-pi", "ada-kpi-runtime"),
        targets=(),
    )
    retained = target / "processes/ada-kpi-runtime"
    for name in distribution.CONSUMER_CONFIGURATION_FILES:
        (retained / name).write_text(f"{name}\n", encoding="utf-8")

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distributed",
        distribution_name="consumer",
        selections=("ada-kpi-runtime",),
        targets=(),
    )

    for name in distribution.CONSUMER_CONFIGURATION_FILES:
        assert (target / "processes/ada-kpi-runtime" / name).read_text() == f"{name}\n"
    assert not (target / "processes/operational-data-pi").exists()


def test_target_expansion_uses_current_source_layouts(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    _write_process(tmp_path, "ada-kpi-runtime")
    _write_process(tmp_path, "operational-data-pi")
    _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    _write_source(
        tmp_path,
        "scopes/operational-data/processes/pi",
        "operational-data-pi",
    )
    _patch_consumer_template(monkeypatch, tmp_path)

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distributed",
        distribution_name="mixed-targets",
        selections=(),
        targets=("ada-backend", "operational-data"),
    )

    manifest = json.loads((target / "distribution.json").read_text(encoding="utf-8"))
    assert {item["name"] for item in manifest["processes"]} == {
        "ada-kpi-runtime",
        "operational-data-pi",
    }
