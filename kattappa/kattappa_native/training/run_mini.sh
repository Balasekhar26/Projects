#!/usr/bin/env bash
# KM-5.0.6 — Kattappa-20M Ignition Test Run
# ===========================================
# Trains the 20M-parameter mini-model on all available corpus data.
# This run verifies: tokenizer, dataloader, training loop,
# checkpointing, and evaluation harness before the full 137M run.
#
# Usage:
#   cd /path/to/kattappa
#   bash kattappa_native/training/run_mini.sh
#
# Expected outcome: val PPL should decrease from ~32000 to <500 over 5000 steps.

set -e  # Exit on error

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHONPATH="$WORKSPACE"
PYTHON="$WORKSPACE/ai_system_env/bin/python3"

echo ""
echo "============================================================"
echo "  Kattappa-20M Ignition Run"
echo "  Model   : 6 layers, d_model=384, 6 heads"
echo "  Params  : ~20M"
echo "  Target  : 1000 steps, batch=4, seq=256"
echo "  Goal    : Verify full pipeline before 137M run"
echo "============================================================"
echo ""

PYTHONUNBUFFERED=1 PYTHONPATH="$PYTHONPATH" "$PYTHON" "$WORKSPACE/kattappa_native/training/trainer.py" \
    --steps          1000    \
    --batch          4       \
    --seq-len        256     \
    --lr             3e-4    \
    --grad-clip      1.0     \
    --eval-interval  100     \
    --log-interval   10      \
    --n-layers       6       \
    --n-heads        6       \
    --d-model        384     \
    --checkpoint-dir "$WORKSPACE/kattappa_native/checkpoints/mini"

echo ""
echo "============================================================"
echo "  Mini run complete. Check val PPL trend above."
echo "  If PPL < 500 and decreasing: ✅ proceed to 137M run."
echo "  If PPL flat or NaN:          ❌ debug training loop first."
echo ""
echo "  Next:"
echo "    bash kattappa_native/training/run_alpha.sh"
echo "============================================================"
echo ""
