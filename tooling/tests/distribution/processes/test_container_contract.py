from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _rules(path: Path) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_process_docker_context_exposes_runtime_inputs_without_detail_files() -> None:
    rules = _rules(REPOSITORY_ROOT / "deployment/processes/.dockerignore")
    allowed = frozenset(rule for rule in rules if rule.startswith("!"))

    assert "!processes/*/secrets.json" in allowed
    assert "!processes/*/config/" in allowed
    assert "!processes/*/config/connections.json" in allowed
    assert all(".detail" not in rule for rule in allowed)
    assert "!processes/*/.env" not in allowed
    assert "!processes/*/config.json" not in allowed


def test_process_dockerfile_uses_filtered_process_root_and_requires_manifest() -> None:
    dockerfile = (
        REPOSITORY_ROOT / "deployment/processes/Dockerfile"
    ).read_text(encoding="utf-8")

    assert "COPY processes/${FILENAME}/ ./" in dockerfile
    assert 'test -f secrets.json || (echo "Process secrets.json not found"' in dockerfile


def test_consumer_gitignore_keeps_distribution_payload_versionable() -> None:
    rules = _rules(
        REPOSITORY_ROOT / "tooling/distribution/processes/consumer/.gitignore"
    )
    ignored = frozenset(rule for rule in rules if not rule.startswith("!"))

    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "!.env.detail" in rules
    assert "wheels/" not in ignored
    assert "uv.lock" not in ignored
    assert ".python-version" not in ignored
    assert "secrets.json" not in ignored
    assert "config.json" not in ignored
    assert "config/connections.json" not in ignored
