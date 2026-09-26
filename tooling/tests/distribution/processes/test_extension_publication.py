from __future__ import annotations

import errno
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "distribution/processes/distribute.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_extension_publish_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
distribution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = distribution
SPEC.loader.exec_module(distribution)


def _extension_inputs(tmp_path: Path):
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src/process.py").write_text("VALUE = 1\n", encoding="utf-8")
    item = SimpleNamespace(
        artifact=SimpleNamespace(root=source, command="operational-data-meteodata"),
        deployment=SimpleNamespace(execution_file="meteodata"),
    )
    manifest = {"name": "e2e-meteodata", "processes": []}
    target = tmp_path / "consumer-output" / "e2e-meteodata.extension.zip"
    target.parent.mkdir()
    return (item,), manifest, target


def test_extension_is_published_from_output_filesystem(
    tmp_path: Path, monkeypatch
) -> None:
    selected, manifest, output = _extension_inputs(tmp_path)
    monkeypatch.setattr(
        distribution,
        "_load_artifact",
        lambda *_args, **_kwargs: SimpleNamespace(command="operational-data-meteodata"),
    )
    original_replace = os.replace

    def reject_cross_directory_publication(source: Path, destination: Path) -> None:
        if Path(destination) == output and Path(source).parent != output.parent:
            raise OSError(errno.EXDEV, "Simulated different filesystems")
        original_replace(source, destination)

    monkeypatch.setattr(distribution.os, "replace", reject_cross_directory_publication)
    result = distribution._package_extension(
        staging_root=tmp_path / "staging",
        selected=selected,
        manifest=manifest,
        output_path=output,
    )
    assert result == output
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read("extension.json")) == manifest
        assert "processes/meteodata/src/process.py" in archive.namelist()
    assert not list(output.parent.glob(".e2e-meteodata.extension-*.zip"))


def test_failed_publication_preserves_existing_zip(tmp_path: Path, monkeypatch) -> None:
    selected, manifest, output = _extension_inputs(tmp_path)
    output.write_bytes(b"previous-extension")
    monkeypatch.setattr(
        distribution,
        "_load_artifact",
        lambda *_args, **_kwargs: SimpleNamespace(command="operational-data-meteodata"),
    )
    original_replace = os.replace

    def fail_publish(source: Path, destination: Path) -> None:
        if Path(destination) == output:
            raise OSError(errno.EACCES, "Simulated publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(distribution.os, "replace", fail_publish)
    with pytest.raises(OSError, match="Simulated publication failure"):
        distribution._package_extension(
            staging_root=tmp_path / "staging",
            selected=selected,
            manifest=manifest,
            output_path=output,
        )
    assert output.read_bytes() == b"previous-extension"
    assert not list(output.parent.glob(".e2e-meteodata.extension-*.zip"))
