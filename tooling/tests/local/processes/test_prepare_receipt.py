from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[3] / "local/processes/process.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_local_prepare_receipt_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
process_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = process_tool
SPEC.loader.exec_module(process_tool)


class BundleStub:
    class ProcessBundleError(RuntimeError):
        pass

    def __init__(self, root: Path) -> None:
        self.root = root
        self.events: list[str] = []

    def resolve_process_root(self, repository_root: Path, value: str) -> Path:
        return self.root

    def process_build_inputs_fingerprint(
        self,
        repository_root: Path,
        process_root: Path,
    ) -> str:
        self.events.append("fingerprint")
        return "sha256:" + "a" * 64

    def build_process_bundle(
        self,
        *,
        repository_root: Path,
        process_root: Path,
        output_root: Path,
    ) -> Path:
        self.events.append("build")
        output = output_root / "sample"
        output.mkdir(parents=True)
        return output

    def write_prepare_receipt(
        self,
        repository_root: Path,
        process_root: Path,
        fingerprint: str,
    ) -> Path:
        self.events.append("receipt")
        path = repository_root / "artifacts/receipts/processes/sample.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}\n", encoding="utf-8")
        return path


def test_prepare_records_receipt_only_after_successful_build(
    tmp_path: Path,
    monkeypatch,
) -> None:
    process_root = tmp_path / "source"
    process_root.mkdir()
    bundle = BundleStub(process_root)
    monkeypatch.setattr(process_tool, "_require_command", lambda name: None)
    arguments = SimpleNamespace(selections=["sample"], all=False)

    process_tool._prepare(arguments, tmp_path, bundle)

    assert bundle.events == ["fingerprint", "build", "fingerprint", "receipt"]
    assert (tmp_path / "artifacts/receipts/processes/sample.json").is_file()
