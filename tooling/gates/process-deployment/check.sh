#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec uv run --no-project python "$SCRIPT_DIR/check.py" "$@"
