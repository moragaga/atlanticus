from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_GENERATOR = (
    Path(__file__).resolve().parents[3] / "distribution/web/generate_starter.py"
)
_spec = importlib.util.spec_from_file_location(
    "generate_web_starter_ada_overlay", _GENERATOR
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)


def test_ada_profile_does_not_inherit_generic_demo_pages_modules_or_docker_probe(
    tmp_path,
    monkeypatch,
) -> None:
    starter = tmp_path / "starter"
    base = starter / "base"
    ada = starter / "ada"
    (base / "src/application/modules/example").mkdir(parents=True)
    (base / "src/application/modules/example/module.py").write_text("GENERIC = True\n")
    (base / "src/application/pages").mkdir(parents=True)
    (base / "src/application/pages/home.py").write_text("GENERIC_HOME = True\n")
    (base / "docker").mkdir(parents=True)
    (base / "docker/verify_wheelhouse.py").write_text("GENERIC_PROBE = True\n")
    (base / ".python-version").write_text("3.14.2\n")
    (ada / "src/application/modules").mkdir(parents=True)
    (ada / "src/application/modules/__init__.py").write_text("ADA_MODULES = True\n")
    (ada / "src/application/pages").mkdir(parents=True)
    (ada / "src/application/pages/home.py").write_text("ADA_HOME = True\n")
    (ada / "docker").mkdir(parents=True)
    (ada / "docker/verify_delivery.py").write_text("ADA_PROBE = True\n")
    contract = (
        tmp_path / "scopes/ada/web/application/ada-generic-application/.env.detail"
    )
    contract.parent.mkdir(parents=True)
    contract.write_text(
        "# @distribution environment\nATLANTICUS_ENVIRONMENT=local\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_module, "STARTER_ROOT", starter)
    monkeypatch.setitem(_module._PRODUCTS["ada"], "starter_overlay", str(ada))
    monkeypatch.setattr(_module, "REPOSITORY_ROOT", tmp_path)

    output = _module.generate_starter(profile="ada", destination=tmp_path / "out")

    assert not (output / "src/application/modules/example").exists()
    assert (
        output / "src/application/modules/__init__.py"
    ).read_text() == "ADA_MODULES = True\n"
    assert (output / "src/application/pages/home.py").read_text() == "ADA_HOME = True\n"
    assert not (output / "docker/verify_wheelhouse.py").exists()
    assert (output / "docker/verify_delivery.py").is_file()
