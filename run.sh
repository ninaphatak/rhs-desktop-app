#!/usr/bin/env bash
# RHS Monitor — macOS/Linux launch script
# Activates the rhs-app conda environment and launches the app.
# If environment.yml has changed since last setup, warns the user.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ENV_NAME="rhs-app"
ENV_FILE="environment.yml"
HASH_FILE=".env_hash"

# Check conda is available
if ! command -v conda &> /dev/null; then
    echo "ERROR: conda not found. Run setup.sh first."
    exit 1
fi

# Check if env exists
if ! conda env list | grep -q "^${ENV_NAME} "; then
    echo "ERROR: '$ENV_NAME' environment not found. Run setup.sh first."
    exit 1
fi

# Check if environment.yml has changed
if [ -f "$HASH_FILE" ]; then
    CURRENT_HASH=$(shasum -a 256 "$ENV_FILE" | cut -d ' ' -f 1)
    SAVED_HASH=$(cat "$HASH_FILE")
    if [ "$CURRENT_HASH" != "$SAVED_HASH" ]; then
        echo "Dependencies changed. Re-run setup.sh first."
        exit 1
    fi
else
    echo "WARNING: No .env_hash found. Run setup.sh to ensure dependencies are up to date."
fi

# Activate and launch
echo "Launching RHS Monitor..."
eval "$(conda shell.bash hook)"
conda activate "$ENV_NAME"
python src/main.py "$@"
