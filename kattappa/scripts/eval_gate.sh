#!/bin/bash
# eval_gate.sh — Kattappa Checkpoint Evaluation and Regression Gate
# Usage: ./scripts/eval_gate.sh <checkpoint_path> [device]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Verify argument
if [ -z "$1" ]; then
    echo "Usage: $0 <checkpoint_path> [device]"
    exit 1
fi

CHECKPOINT_PATH="$1"
DEVICE="${2:-cpu}"

# Navigate to workspace
cd "$WORKSPACE_ROOT"

# Ensure venv exists
if [ ! -d "ai_system_env" ]; then
    echo "Error: Virtual environment 'ai_system_env' not found in $WORKSPACE_ROOT."
    exit 1
fi

echo "======================================================================"
echo " Starting Kattappa Evaluation and Regression Gate"
echo " Target Checkpoint: $CHECKPOINT_PATH"
echo " Device:            $DEVICE"
echo "======================================================================"

# Run eval using virtual env python
./ai_system_env/bin/python3 run_eval.py --checkpoint "$CHECKPOINT_PATH" --device "$DEVICE"

echo "======================================================================"
echo " Evaluation Gate PASSED successfully."
echo "======================================================================"
