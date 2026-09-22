from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "distribution/processes/consumer/process.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_consumer_process_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consumer
SPEC.loader.exec_module(consumer)


def _distribution(root: Path, *, with_env: bool) -> None:
    (root / "processes/sample/wheels").mkdir(parents=True)
    (root / "processes/sample/src").mkdir()
    (root / "processes/sample/pyproject.toml").write_text("", encoding="utf-8")
    (root / "processes/sample/uv.lock").write_text("", encoding="utf-8")
    if with_env:
        (root / "processes/sample/.env").write_text(
            "ENVIRONMENT=local\n", encoding="utf-8"
        )
    (root / "distribution.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "sample",
                "processes": [
                    {
                        "name": "sample",
                        "project": "sample-package",
                        "version": "1.0.0",
                        "system_profile": "base",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    marker = 'x-atlanticus-distribution-contract: "1"\nservices:\n  sample:\n'
    (root / "compose.yaml").write_text(marker, encoding="utf-8")
    (root / "compose.bind.yaml").write_text(marker, encoding="utf-8")
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")


def test_validate_requires_local_environment(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=False)

    try:
        consumer._validate_distribution(tmp_path, require_environment=True)
    except consumer.ConsumerProcessError as error:
        assert "Local process .env file not found" in str(error)
    else:
        raise AssertionError("Expected missing .env to fail validation")


def test_validate_accepts_complete_distribution(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=True)

    assert consumer._validate_distribution(tmp_path, require_environment=True) == (
        "sample",
    )
