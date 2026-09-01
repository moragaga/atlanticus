from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _prepare_wrapper(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(
        REPOSITORY_ROOT / "scripts/local-process.sh", scripts / "local-process.sh"
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv = fake_bin / "uv"
    uv.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$UV_ARGS_FILE"\n', encoding="utf-8"
    )
    uv.chmod(0o755)

    args_file = tmp_path / "uv-args.txt"
    environ = dict(os.environ)
    environ["PATH"] = f"{fake_bin}{os.pathsep}{environ.get('PATH', '')}"
    environ["UV_ARGS_FILE"] = str(args_file)
    return scripts / "local-process.sh", args_file, environ


def _run_prepare(
    tmp_path: Path, *arguments: str
) -> tuple[subprocess.CompletedProcess[str], tuple[str, ...]]:
    wrapper, args_file, environ = _prepare_wrapper(tmp_path)
    result = subprocess.run(
        ("bash", str(wrapper), "prepare", *arguments),
        cwd=wrapper.parents[1],
        env=environ,
        check=False,
        capture_output=True,
        text=True,
    )
    uv_arguments = (
        tuple(args_file.read_text(encoding="utf-8").splitlines())
        if args_file.is_file()
        else ()
    )
    return result, uv_arguments


def test_prepare_requires_explicit_selection(tmp_path: Path) -> None:
    result, uv_arguments = _run_prepare(tmp_path)

    assert result.returncode == 1
    assert uv_arguments == ()
    assert "prepare [--scope SCOPE] --all|PROCESS" in result.stderr


def test_prepare_scope_all_forwards_scope_without_empty_array(tmp_path: Path) -> None:
    result, uv_arguments = _run_prepare(
        tmp_path, "--scope", "operational-data", "--all"
    )

    assert result.returncode == 0
    assert "--scope" in uv_arguments
    assert "operational-data" in uv_arguments
    assert "--all" not in uv_arguments
    assert "deployment/processes/bundle.py" in " ".join(uv_arguments)


def test_prepare_selected_processes_forwards_commands(tmp_path: Path) -> None:
    result, uv_arguments = _run_prepare(
        tmp_path,
        "operational-data-pi",
        "operational-data-dispatch",
    )

    assert result.returncode == 0
    assert "operational-data-pi" in uv_arguments
    assert "operational-data-dispatch" in uv_arguments


def test_prepare_rejects_scope_all_mixed_with_processes(tmp_path: Path) -> None:
    result, uv_arguments = _run_prepare(
        tmp_path,
        "--scope",
        "operational-data",
        "--all",
        "operational-data-pi",
    )

    assert result.returncode == 1
    assert uv_arguments == ()


def test_wrapper_exposes_separate_prepare_validate_and_docker_execution() -> None:
    shell = (REPOSITORY_ROOT / "scripts/local-process.sh").read_text(encoding="utf-8")

    assert "command_prepare()" in shell
    assert "command_validate()" in shell
    assert "command_build()" in shell
    assert "command_up()" in shell
    assert "Usage: scripts/local-process.sh build [--bind]" in shell
    assert "compose build --no-cache" in shell
    assert "compose up -d" in shell
    assert 'compose run --rm "${process}" --run-once' in shell
    assert "deployment/processes/bundle.py" in shell
    assert "scopes/ada/scripts/processes" not in shell
    assert "${processes[@]}" not in shell
