#!/usr/bin/env bash
# KM-5 — Kattappa-137M Full Alpha Run
# =====================================
# Full pre-training on the expanded corpus with SafetyController gating.
# ⚠ REQUIRES:
#   1. corpus_builder.py run complete (≥50M tokens)
#   2. tokenizer_eval.py passed (Telugu fertility < 3.0)
#   3. Kattappa-20M mini run successful (val PPL < 500)
#
# Usage:
#   bash kattappa_native/training/run_alpha.sh

set -e

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$WORKSPACE/ai_system_env/bin/python3"

echo ""
echo "============================================================"
echo "  Kattappa-137M Full Alpha Run (Proactively Gated)"
echo "  Model   : 12 layers, d_model=768, 12 heads"
echo "  Params  : ~137M"
echo "  Target  : 50000 steps, batch=2 (or dynamically managed)"
echo "  Safety  : strict (8.4 GB memory limit, curriculum enabled)"
echo "============================================================"
echo ""

PYTHONUNBUFFERED=1 PYTHONPATH="$WORKSPACE" "$PYTHON" "$WORKSPACE/kattappa_native/training/trainer.py" \
    --steps          50000   \
    --batch          2       \
    --seq-len        2048    \
    --initial-seq-len 256    \
    --curriculum             \
    --kattappa-budget-gb 8.4 \
    --safety-mode    strict  \
    --lr             3e-4    \
    --grad-clip      1.0     \
    --eval-interval  200     \
    --log-interval   10      \
    --n-layers       12      \
    --n-heads        12      \
    --d-model        768     \
    --checkpoint-dir "$WORKSPACE/kattappa_native/checkpoints/alpha"
