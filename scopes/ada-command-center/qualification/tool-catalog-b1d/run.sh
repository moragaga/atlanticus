#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
manager="$root/scopes/ada-command-center/web/application/ada-command-center-configuration-manager"
qualification="$root/scopes/ada-command-center/qualification/tool-catalog-b1d"
cd "$manager"
export PYTHONPATH="$qualification${PYTHONPATH:+:$PYTHONPATH}"
if [[ "${1:-}" == "test" ]]; then
    shift
    uv run --group dev --with-editable "$root/scopes/ada/web/tools/persistence" \
        python -m pytest "$qualification/tests" "$@"
elif [[ "${1:-}" == "lint" ]]; then
    shift
    uv run --group dev --with-editable "$root/scopes/ada/web/tools/persistence" \
        ruff check --config "$manager/pyproject.toml" \
        "$qualification/qualify.py" "$qualification/tests" "$@"
elif [[ "${1:-}" == "format-check" ]]; then
    shift
    uv run --group dev --with-editable "$root/scopes/ada/web/tools/persistence" \
        ruff format --check --config "$manager/pyproject.toml" \
        "$qualification/qualify.py" "$qualification/tests" "$@"
else
    uv run --group dev --with-editable "$root/scopes/ada/web/tools/persistence" \
        python "$qualification/qualify.py" "$@"
fi
