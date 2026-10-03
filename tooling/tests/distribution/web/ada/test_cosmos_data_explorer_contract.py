from __future__ import annotations

from pathlib import Path


_STARTER = (
    Path(__file__).resolve().parents[5]
    / "scopes/ada/tooling/distribution/web/starter"
)


def test_cosmos_data_explorer_is_enabled_and_loopback_bound() -> None:
    explorer_port = "127.0.0.1:${ADA_COSMOS_EXPLORER_PORT:-1234}:1234"

    for profile in ("infra", "full"):
        compose = (_STARTER / f"deployment/compose/{profile}.yaml").read_text(
            encoding="utf-8"
        )

        assert "ENABLE_EXPLORER: 'true'" in compose
        assert explorer_port in compose
