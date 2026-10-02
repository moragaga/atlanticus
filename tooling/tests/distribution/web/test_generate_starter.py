from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_GENERATOR = (
    Path(__file__).resolve().parents[3] / "distribution/web/generate_starter.py"
)
_spec = importlib.util.spec_from_file_location("generate_web_starter", _GENERATOR)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
generate_starter = _module.generate_starter


@pytest.fixture
def source(tmp_path, monkeypatch):
    starter = tmp_path / "starter"
    base = starter / "base"
    ada = starter / "ada"
    base.mkdir(parents=True)
    ada.mkdir(parents=True)
    (base / ".python-version").write_text("3.14.2\n", encoding="utf-8")
    (base / ".env.detail").write_text("GENERIC_VARIABLE=value\n", encoding="utf-8")
    (base / "pyproject.toml").write_text(
        '[project]\nname="generic"\n', encoding="utf-8"
    )
    (ada / "pyproject.toml").write_text('[project]\nname="ada"\n', encoding="utf-8")
    (ada / "src").mkdir()
    (ada / "src" / "demo.py").write_text("value = True\n", encoding="utf-8")
    cache = ada / ".ruff_cache/0.15.22"
    cache.mkdir(parents=True)
    (cache / "fixture").write_text("local-cache", encoding="utf-8")
    contract = (
        tmp_path / "scopes/ada/web/application/ada-generic-application/.env.detail"
    )
    contract.parent.mkdir(parents=True)
    contract.write_text(
        "# Documentation\n"
        "# @distribution environment\nATLANTICUS_ENVIRONMENT=local\n"
        "# @distribution manual-default\nADA_PERSISTENCE_MODE=durable\n"
        "# @distribution manual\nADA_TOOL_NAMESPACE=<tool-namespace>\n"
        "# @distribution key-vault secret-cosmos-primary-key\n"
        "ADA_TOOL_PROJECTION_COSMOS_KEY=<cosmos-key>\n"
        "# @distribution key-vault secret-ada-storage-connection-string\n"
        "ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING=<connection-string>\n"
        "# Optional alternative is not activated.\n"
        "# ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL=<account-url>\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_module, "STARTER_ROOT", starter)
    monkeypatch.setitem(_module._PRODUCTS["ada"], "starter_overlay", str(ada))
    monkeypatch.setattr(_module, "REPOSITORY_ROOT", tmp_path)
    return contract


def _csv(path: Path) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
    reader.fieldnames = [name.strip() for name in reader.fieldnames or ()]
    records = list(reader)
    assert records[-1] == {
        "envName": "END_NO_READ",
        "secretReference": "",
        "explicitValue": "",
    }
    return records[:-1]


@pytest.mark.parametrize("profile", ("generic", "ada"))
def test_starter_is_reproducible_and_manifest_matches_files(source, tmp_path, profile):
    first = generate_starter(profile=profile, destination=tmp_path / "first")
    second = generate_starter(profile=profile, destination=tmp_path / "second")
    payload = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert payload == json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert payload["profile"] == profile
    assert payload["qualification"] == "UNVERIFIED"
    assert payload["wheelhouse_included"] is False
    assert {
        name: hashlib.sha256((first / name).read_bytes()).hexdigest()
        for name in payload["files"]
    } == payload["files"]
    assert (first / ".python-version").read_text(encoding="utf-8").strip() == "3.14.2"
    assert not any(".ruff_cache" in name for name in payload["files"])
    if profile == "ada":
        assert (first / ".env.detail").read_bytes() == source.read_bytes()
        assert len(payload["configuration_templates"]) == 4
        assert (first / "src/demo.py").is_file()
    else:
        assert (first / ".env.detail").read_text() == "GENERIC_VARIABLE=value\n"
        assert payload["configuration_templates"] == []
        assert not (first / "configuration").exists()
    assert not (first / ".env").exists()


def test_ada_generates_all_configuration_formats_without_extra_inputs(source, tmp_path):
    app = generate_starter(profile="ada", destination=tmp_path / "out")
    for env in ("dev", "uat", "prd"):
        assert (app / f"configuration/templates/{env}.mapping-env.csv").is_file()
    assert (app / "configuration/templates/secrets.json").is_file()
    assert not (app / "secrets.json").exists()
    manifest = json.loads((app / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(manifest["configuration_templates"]) == sorted(
        name
        for name in manifest["files"]
        if name.startswith("configuration/templates/")
    )


def test_mapping_files_end_with_exact_pipeline_marker(source, tmp_path):
    app = generate_starter(profile="ada", destination=tmp_path / "out")
    for env in ("dev", "uat", "prd"):
        content = (app / f"configuration/templates/{env}.mapping-env.csv").read_text(
            encoding="utf-8"
        )
        assert content.splitlines()[-1] == "END_NO_READ,,"
        assert content.endswith("END_NO_READ,,")
        assert content.count("END_NO_READ") == 1
    assert "END_NO_READ" not in (
        app / "configuration/templates/secrets.json"
    ).read_text(encoding="utf-8")


def test_environment_and_persistence_are_generated_for_every_stage(source, tmp_path):
    app = generate_starter(profile="ada", destination=tmp_path / "out")
    dev = {
        row["envName"]: row
        for row in _csv(app / "configuration/templates/dev.mapping-env.csv")
    }
    uat = {
        row["envName"]: row
        for row in _csv(app / "configuration/templates/uat.mapping-env.csv")
    }
    prd = {
        row["envName"]: row
        for row in _csv(app / "configuration/templates/prd.mapping-env.csv")
    }

    assert dev["ATLANTICUS_ENVIRONMENT"]["explicitValue"] == "local"
    assert uat["ATLANTICUS_ENVIRONMENT"]["explicitValue"] == "production"
    assert prd["ATLANTICUS_ENVIRONMENT"]["explicitValue"] == "production"
    for entries in (dev, uat, prd):
        assert entries["ADA_PERSISTENCE_MODE"]["explicitValue"] == "durable"
        assert entries["ADA_TOOL_NAMESPACE"]["explicitValue"] == ""


def test_secrets_contract_contains_only_concrete_key_vault_requirements(
    source, tmp_path
):
    app = generate_starter(profile="ada", destination=tmp_path / "out")
    records = json.loads((app / "configuration/templates/secrets.json").read_text())
    assert records == [
        {
            "var_name": "ADA_TOOL_PROJECTION_COSMOS_KEY",
            "secret_name": "secret-cosmos-primary-key",
            "required_in_key_vault": True,
        },
        {
            "var_name": "ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING",
            "secret_name": "secret-ada-storage-connection-string",
            "required_in_key_vault": True,
        },
    ]
    assert all("<" not in row["secret_name"] for row in records)


def test_mappings_and_json_do_not_publish_inactive_alternatives(source, tmp_path):
    app = generate_starter(profile="ada", destination=tmp_path / "out")
    names = [entry.name for entry in _module._environment_entries(source)]
    for env in ("dev", "uat", "prd"):
        records = _csv(app / f"configuration/templates/{env}.mapping-env.csv")
        assert [row["envName"] for row in records] == names
    assert "ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL" not in names


@pytest.mark.parametrize(
    "replacement,match",
    (
        ("ADA_PERSISTENCE_MODE=durable", "no distribution declaration"),
        (
            "# @distribution manual-default\nADA_PERSISTENCE_MODE=<unset>",
            "Unsafe environment default",
        ),
        (
            "# @distribution key-vault secret-cosmos-primary-key\nADA_TOOL_PROJECTION_COSMOS_KEY=plaintext",
            "exposes a credential",
        ),
        (
            "# @distribution key-vault <placeholder>\nADA_TOOL_PROJECTION_COSMOS_KEY=<cosmos-key>",
            "must be concrete",
        ),
    ),
)
def test_invalid_contract_blocks_before_creating_distribution(
    source,
    tmp_path,
    replacement,
    match,
):
    text = source.read_text(encoding="utf-8")
    if replacement == "ADA_PERSISTENCE_MODE=durable":
        text = text.replace(
            "# @distribution manual-default\nADA_PERSISTENCE_MODE=durable", replacement
        )
    elif "ADA_PERSISTENCE_MODE" in replacement:
        text = text.replace(
            "# @distribution manual-default\nADA_PERSISTENCE_MODE=durable", replacement
        )
    else:
        text = text.replace(
            "# @distribution key-vault secret-cosmos-primary-key\n"
            "ADA_TOOL_PROJECTION_COSMOS_KEY=<cosmos-key>",
            replacement,
        )
    source.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        generate_starter(profile="ada", destination=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_existing_destination_is_not_overwritten(source, tmp_path):
    path = tmp_path / "out"
    generate_starter(profile="ada", destination=path)
    before = (path / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        generate_starter(profile="ada", destination=path)
    assert (path / "manifest.json").read_bytes() == before


def test_real_ada_contract_uses_one_persistence_decision_and_no_manual_master_path():
    real = (
        _GENERATOR.parents[3]
        / "scopes/ada/web/application/ada-generic-application/.env.detail"
    )
    if not real.is_file():
        pytest.skip("ADA Generic project contract is not mounted for this test")
    entries = _module._environment_entries(real)
    names = {entry.name for entry in entries}
    assert "ADA_PERSISTENCE_MODE" in names
    assert "ADA_TOOL_SOURCE_PROVIDER" not in names
    assert "ADA_TOOL_PROJECTION_PROVIDER" not in names
    assert "ADA_MASTER_PROJECTION_MATERIAL_PATH" not in names


def test_generator_commented_mirror_is_ast_equivalent():
    root = _GENERATOR.parent
    assert ast.dump(
        ast.parse(_GENERATOR.read_text()), include_attributes=False
    ) == ast.dump(
        ast.parse((root / "commented/generate_starter.py").read_text()),
        include_attributes=False,
    )
