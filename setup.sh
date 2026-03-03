#!/usr/bin/env bash
# RHS Monitor — macOS/Linux setup script
# Creates (or updates) the rhs-app conda environment from environment.yml

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_NAME="rhs-app"
ENV_FILE="environment.yml"
HASH_FILE=".env_hash"

echo "=== RHS Monitor Setup ==="

# Check conda is available
if ! command -v conda &> /dev/null; then
    echo "ERROR: conda not found. Install Miniconda or Anaconda first."
    echo "  https://docs.anaconda.com/miniconda/"
    exit 1
fi

# Compute current hash of environment.yml
CURRENT_HASH=$(shasum -a 256 "$ENV_FILE" | cut -d ' ' -f 1)

# Check if env exists
if conda env list | grep -q "^${ENV_NAME} "; then
    echo "Updating existing '$ENV_NAME' environment..."
    conda env update -n "$ENV_NAME" -f "$ENV_FILE" --prune
else
    echo "Creating '$ENV_NAME' environment..."
    conda env create -f "$ENV_FILE"
fi

# Write hash
echo "$CURRENT_HASH" > "$HASH_FILE"

echo ""
echo "Setup complete. Run the app with:"
echo "  bash run.sh"
