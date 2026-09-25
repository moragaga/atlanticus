#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec uv run --python 3.14.2 --no-python-downloads --no-project python "$SCRIPT_DIR/process.py" "$@"
