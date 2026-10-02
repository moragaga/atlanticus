from __future__ import annotations

from pathlib import Path


_STARTER = (
    Path(__file__).resolve().parents[5] / "scopes/ada/tooling/distribution/web/starter"
)


def test_full_compose_web_does_not_wait_for_resource_job_success():
    content = (_STARTER / "deployment/compose/full.yaml").read_text(encoding="utf-8")
    web = content.split("\n  web:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    depends = web.split("\n    depends_on:\n", 1)[1].split("\n    ports:\n", 1)[0]
    assert "resources:" not in depends
    assert "cosmos-emulator:" in depends
    assert "azurite:" in depends
    assert depends.count("condition: service_started") == 2
