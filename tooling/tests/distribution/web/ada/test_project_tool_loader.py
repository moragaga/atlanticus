from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

_SOURCE = (
    Path(__file__).resolve().parents[5]
    / "scopes/ada/tooling/distribution/web/starter/tooling/project.py"
)


def _distributed_loader(tmp_path: Path, *, tampered: bool = False):
    root = tmp_path / "application"
    tooling = root / "tooling"
    wheelhouse = root / "wheelhouse"
    tooling.mkdir(parents=True)
    wheelhouse.mkdir()
    loader = tooling / "project.py"
    loader.write_bytes(_SOURCE.read_bytes())
    wheel = wheelhouse / "ada_project_tooling-0.1.0-py3-none-any.whl"
    implementation = (
        "from pathlib import Path\n"
        "class ProjectError(RuntimeError): pass\n"
        "def _check_environment(root): return root\n"
        "def _locked(root): return root\n"
        'def _python(root): return root / ".venv/bin/python"\n'
        "def main(argv=None, *, root: Path):\n"
        "    global CALLED_ROOT\n"
        "    CALLED_ROOT = root\n"
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("ada_project_tooling/cli.py", implementation)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (wheelhouse / "manifest.json").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "name": "ada-project-tooling",
                        "version": "0.1.0",
                        "filename": wheel.name,
                        "sha256": digest,
                    }
                ],
            }
        )
    )
    if tampered:
        with wheel.open("ab") as stream:
            stream.write(b"tampered")
    spec = importlib.util.spec_from_file_location("distributed_project_loader", loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    return spec, module, root


def test_loader_executes_verified_project_tooling_wheel_with_explicit_project_root(
    tmp_path,
):
    spec, module, root = _distributed_loader(tmp_path)
    spec.loader.exec_module(module)
    assert module._root() == root
    module.main(["sync"])
    assert module.CALLED_ROOT == root


def test_loader_rejects_tampered_project_tooling_before_execution(tmp_path):
    spec, module, _root = _distributed_loader(tmp_path, tampered=True)
    with pytest.raises(RuntimeError, match="integrity failed"):
        spec.loader.exec_module(module)
