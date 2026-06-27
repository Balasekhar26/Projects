#!/usr/bin/env bash
# ─── TEST 6: Full Production ─────────────────────────────────────────────────
# All subsystems enabled: training + checkpoint + eval + monitor at 1s.

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$WORKSPACE/ai_system_env/bin/python3"

echo "============================================================"
echo "  ISOLATION TEST 6: Full Production (all subsystems)"
echo "============================================================"

# Prepare clean independent checkpoint directory if not resuming
# We preserve checkpoints to allow resuming.
mkdir -p "$WORKSPACE/kattappa_native/checkpoints/test6"

# Prepare clean logs directory
mkdir -p "$WORKSPACE/logs/test6"

# Generate metadata.json
GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
CONFIG_HASH=$(shasum -a 256 "$WORKSPACE/kattappa_native/training/trainer.py" 2>/dev/null | awk '{print $1}' || echo "unknown")
TOKENIZER_VERSION="tokenizer-v1"
DATASET_VERSION="corpus-v1"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat <<EOF > "$WORKSPACE/logs/test6/metadata.json"
{
  "git_commit": "$GIT_COMMIT",
  "config_hash": "$CONFIG_HASH",
  "tokenizer_version": "$TOKENIZER_VERSION",
  "dataset_version": "$DATASET_VERSION",
  "checkpoint_path": "$WORKSPACE/kattappa_native/checkpoints/test6",
  "safety_mode": "monitor",
  "timestamp": "$TIMESTAMP"
}
EOF

# Execute
PYTHONUNBUFFERED=1 PYTHONPATH="$WORKSPACE" "$PYTHON" \
    "$WORKSPACE/kattappa_native/training/trainer.py" \
    --steps          50000   \
    --batch          2       \
    --seq-len        1024    \
    --initial-seq-len 256   \
    --curriculum             \
    --kattappa-budget-gb 9.5 \
    --safety-mode    monitor \
    --lr             3e-4    \
    --grad-clip      1.0     \
    --eval-interval  100     \
    --log-interval   10      \
    --n-layers       12      \
    --n-heads        12      \
    --d-model        768     \
    --checkpoint-dir "$WORKSPACE/kattappa_native/checkpoints/test6" \
    --resume         true    \
    --timeline-log-path "$WORKSPACE/logs/test6/training_step_timeline.csv" \
    --timing-log-path "$WORKSPACE/logs/test6/checkpoint_timing.jsonl"
