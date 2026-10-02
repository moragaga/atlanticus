#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"
exec uv run --python 3.14.2 --no-python-downloads --no-sync python "$SCRIPT_DIR/check.py" "$@"
