from __future__ import annotations

from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_ROOT = _REPOSITORY_ROOT / "tooling/distribution/web"
_ADA = _REPOSITORY_ROOT / "scopes/ada/tooling/distribution/web"
_COMMANDS = (
    (_ROOT / "generate_starter", "generate_starter.py", False),
    (_ROOT / "build_wheelhouse", "build_wheelhouse.py", True),
    (_ROOT / "qualify_starter", "qualify_starter.py", False),
    (_ADA / "build_distribution", "build_distribution.py", True),
    (_ADA / "qualify_distribution", "qualify_distribution.py", True),
)


@pytest.mark.parametrize(("command", "implementation", "packaging"), _COMMANDS)
def test_human_web_tooling_has_portable_launchers(
    command: Path,
    implementation: str,
    packaging: bool,
) -> None:
    shell = command.with_suffix(".sh").read_text(encoding="utf-8")
    windows = command.with_suffix(".cmd").read_text(encoding="utf-8")
    prefix = "uv run --python 3.14.2 --no-python-downloads --no-project"
    assert prefix in shell
    assert prefix in windows
    assert implementation in shell
    assert implementation in windows
    assert '"$@"' in shell
    assert "%*" in windows
    assert ("--with packaging==25.0" in shell) is packaging
    assert ("--with packaging==25.0" in windows) is packaging
