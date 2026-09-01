#!/usr/bin/env bash
set -euo pipefail

echo "Atlanticus compress started"

./clean_root.sh

zip -r "atlanticus-latest-version-1.0.0-$(date +%Y%m%d-%H%M%S).zip" . -x "*venv*" "*.idea*" "*.git*" "*.env*" "*.DS_Store*" ".local-assets*" ".local-data*" "*.runtime*" "artifacts" ".zip"
echo "Atlanticus compress completed successfully."
