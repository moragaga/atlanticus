from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_RUNTIME = (
    Path(__file__).resolve().parents[5]
    / "scopes/ada/tooling/distribution/web/starter/src/application/runtime.py"
)


def _package(monkeypatch, name: str, **members):
    parts = name.split(".")
    for index in range(1, len(parts)):
        parent = ".".join(parts[:index])
        if parent not in sys.modules:
            module = ModuleType(parent)
            module.__path__ = []
            monkeypatch.setitem(sys.modules, parent, module)
    module = ModuleType(name)
    module.__dict__.update(members)
    monkeypatch.setitem(sys.modules, name, module)


def test_ada_starter_runtime_only_delegates_host_extensions(monkeypatch) -> None:
    calls = []

    def create_worker_runtime(**kwargs):
        calls.append(("worker", kwargs))
        return object()

    def run_operational_application(**kwargs):
        calls.append(("run", kwargs))

    _package(
        monkeypatch,
        "ada.web.application.generic.host",
        create_worker_runtime=create_worker_runtime,
        run_operational_application=run_operational_application,
    )

    def composition(*_args):
        return None

    def identity():
        return None

    _package(monkeypatch, "application.composition", create_composition=composition)
    _package(monkeypatch, "application.production", create_identity_provider=identity)

    spec = importlib.util.spec_from_file_location("ada_starter_runtime", _RUNTIME)
    assert spec is not None and spec.loader is not None
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)

    assert runtime.create_worker_runtime() is not None
    runtime.run_application()
    assert calls == [
        (
            "worker",
            {
                "composition_factory": composition,
                "production_identity_provider_factory": identity,
            },
        ),
        (
            "run",
            {
                "composition_factory": composition,
                "production_identity_provider_factory": identity,
            },
        ),
    ]
