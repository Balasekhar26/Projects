#!/usr/bin/env bash
# Safety Gated Launcher — Step 30
# ================================
# Performs safety health checks on Apple Silicon before launching the trainer.
# Prevents starting under pre-existing memory pressure or heavy swap.

set -e

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$WORKSPACE/ai_system_env/bin/python3"

echo "============================================================"
echo "  Kattappa Pre-flight Safety Checks"
echo "============================================================"

# 1. Check memory pressure level (Strict: must be NOMINAL/Green, i.e. level >= 80)
if [ -f /usr/sbin/sysctl ]; then
    MEM_LEVEL=$(sysctl -n kern.memorystatus_level)
    echo "• macOS memorystatus level: $MEM_LEVEL / 100"
    if [ "$MEM_LEVEL" -lt 80 ]; then
        echo "❌ ERROR: macOS memory pressure is elevated (level < 80)."
        echo "   Please close other heavy applications to return to NOMINAL (Green) before starting."
        exit 1
    fi
fi

# 2. Check existing swap files
SWAP_FILES=0
for path in "/System/Volumes/VM" "/private/var/vm"; do
    if [ -d "$path" ]; then
        FILES_COUNT=$(ls -1 "$path"/swapfile* 2>/dev/null | wc -l || echo 0)
        SWAP_FILES=$((SWAP_FILES + FILES_COUNT))
    fi
done

echo "• Active swap files: $SWAP_FILES"
if [ "$SWAP_FILES" -gt 3 ]; then
    echo "❌ ERROR: System has too many active swap files ($SWAP_FILES)."
    echo "   Unified memory pressure is too high. Reboot your Mac or free up RAM first."
    exit 1
fi

# 3. Check swap usage (must be <= 1.0 GB)
if [ -f /usr/sbin/sysctl ]; then
    SWAP_USAGE=$(sysctl -n vm.swapusage)
    echo "• Swap Usage: $SWAP_USAGE"
    # Parse swap usage in megabytes
    SWAP_USED_MB=$(echo "$SWAP_USAGE" | sed -E 's/.*used = ([0-9.]+)M.*/\1/')
    if (( $(echo "$SWAP_USED_MB > 1024.0" | bc -l) )); then
        echo "❌ ERROR: Swap usage exceeds 1.0 GB ($SWAP_USED_MB MB)."
        echo "   Please clear active RAM before running training."
        exit 1
    fi
fi

# 4. Check SSD free space (must be >= 5 GB)
if [ -d "/" ]; then
    # Get free space in GB on macOS
    FREE_SPACE_KB=$(df / | tail -1 | awk '{print $4}')
    FREE_SPACE_GB=$((FREE_SPACE_KB / 1024 / 1024))
    echo "• Boot volume free space: ${FREE_SPACE_GB} GB"
    if [ "$FREE_SPACE_GB" -lt 5 ]; then
        echo "❌ ERROR: Boot volume free space is less than 5 GB (${FREE_SPACE_GB} GB)."
        echo "   Free up disk space before launching training."
        exit 1
    fi
fi

echo "✅ Pre-flight safety checks passed!"
echo "🚀 Launching trainer in strict safety mode..."
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
    --eval-interval  100     \
    --log-interval   10      \
    --n-layers       12      \
    --n-heads        12      \
    --d-model        768     \
    --checkpoint-dir "$WORKSPACE/kattappa_native/checkpoints/alpha"
